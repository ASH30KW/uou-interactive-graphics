#![feature(generic_associated_types)]
#![feature(portable_simd)]
mod shader_bindings;

use metal_app::{
    components::{Camera, DepthTexture, ShadingModeSelector},
    metal::*,
    metal_types::*,
    pipeline::*,
    *,
};
use shader_bindings::*;
use std::{
    f32::consts::PI,
    ops::Neg,
    path::PathBuf,
    simd::{f32x2, SimdFloat},
};

const DEFAULT_AMBIENT_AMOUNT: f32 = 0.15;
const INITIAL_CAMERA_ROTATION: f32x2 = f32x2::from_array([-PI / 6., 0.]);
const INITIAL_LIGHT_ROTATION: f32x2 = f32x2::from_array([-PI / 4., 0.]);
const LIBRARY_BYTES: &'static [u8] = include_bytes!(concat!(env!("OUT_DIR"), "/shaders.metallib"));
const LIGHT_DISTANCE: f32 = 0.5;

struct Delegate {
    bg_render_pipeline: RenderPipeline<1, bg_vertex, bg_fragment, (Depth, NoStencil)>,
    camera: Camera,
    command_queue: CommandQueue,
    cubemap_texture: Texture,
    depth_state: DepthStencilState,
    depth_read_only: DepthStencilState,
    depth_texture: DepthTexture,
    device: Device,
    library: Library,
    light_pipeline: RenderPipeline<1, light_vertex, light_fragment, (Depth, NoStencil)>,
    light: Camera,
    m_model_to_world: f32x4x4,
    model_pipeline: RenderPipeline<1, main_vertex, main_fragment, (Depth, NoStencil)>,
    model_space: ModelSpace,
    model: Model<Geometry, HasMaterial<Material>>,
    needs_render: bool,
    reflectivity: f32,
    shading_mode: ShadingModeSelector,
}

fn create_model_pipeline(
    device: &Device,
    library: &Library,
    shading_mode: ShadingModeSelector,
) -> RenderPipeline<1, main_vertex, main_fragment, (Depth, NoStencil)> {
    RenderPipeline::new(
        "Model",
        &device,
        &library,
        [(DEFAULT_COLOR_FORMAT, BlendMode::NoBlend)],
        main_vertex,
        main_fragment {
            HasAmbient: shading_mode.has_ambient(),
            HasDiffuse: shading_mode.has_diffuse(),
            OnlyNormals: shading_mode.only_normals(),
            HasSpecular: shading_mode.has_specular(),
        },
        (Depth(DEFAULT_DEPTH_FORMAT), NoStencil),
    )
}

impl RendererDelgate for Delegate {
    fn new(device: Device) -> Self {
        let cubemap_texture = debug_time("proj9 - Load Bedroom Cube Texture", || {
            asset_compiler::cube_texture::load_cube_texture_asset_dir(
                &device,
                &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("assets/cubemap.asset"),
            )
        });

        let model_file = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("common-assets")
            .join("chair")
            .join("chair.obj");

        let library = device
            .new_library_with_data(LIBRARY_BYTES)
            .expect("Failed to import shader metal lib.");
        let shading_mode = ShadingModeSelector::DEFAULT;
        let model_pipeline = create_model_pipeline(&device, &library, shading_mode);
        let model = Model::from_file(
            model_file,
            &device,
            |arg: &mut Geometry,
             GeometryToEncode {
                 indices_buffer,
                 positions_buffer,
                 normals_buffer,
                 tx_coords_buffer,
                 ..
             }| {
                arg.indices = indices_buffer;
                arg.positions = positions_buffer;
                arg.normals = normals_buffer;
                arg.tx_coords = tx_coords_buffer;
            },
            HasMaterial(
                |arg: &mut Material,
                 MaterialToEncode {
                     ambient_texture,
                     diffuse_texture,
                     specular_texture,
                     specular_shineness,
                 }| {
                    arg.ambient_texture = ambient_texture;
                    arg.diffuse_texture = diffuse_texture;
                    arg.specular_texture = specular_texture;
                    arg.specular_shineness = specular_shineness;
                    arg.ambient_amount = DEFAULT_AMBIENT_AMOUNT;
                },
            ),
        );
        let &MaxBounds { center, size } = &model.geometry_max_bounds;
        let &[cx, cy, cz, _] = center.neg().as_array();
        let scale = 1. / size.reduce_max();
        let m_model_to_world = (f32x4x4::scale(scale, scale, scale, 1.)
            * (f32x4x4::y_rotate(PI) * f32x4x4::x_rotate(PI / 2.)))
            * f32x4x4::translate(cx, cy, cz);

        Self {
            bg_render_pipeline: RenderPipeline::new(
                "BG",
                &device,
                &library,
                [(DEFAULT_COLOR_FORMAT, BlendMode::NoBlend)],
                bg_vertex,
                bg_fragment,
                (Depth(DEFAULT_DEPTH_FORMAT), NoStencil),
            ),
            camera: Camera::new_with_default_distance(
                INITIAL_CAMERA_ROTATION,
                ModifierKeys::empty(),
                false,
                0.,
            ),
            command_queue: device.new_command_queue(),
            cubemap_texture,
            depth_state: {
                let desc = DepthStencilDescriptor::new();
                desc.set_depth_compare_function(MTLCompareFunction::LessEqual);
                desc.set_depth_write_enabled(true);
                device.new_depth_stencil_state(&desc)
            },
            depth_read_only: {
                let desc = DepthStencilDescriptor::new();
                desc.set_depth_compare_function(MTLCompareFunction::LessEqual);
                desc.set_depth_write_enabled(false);
                device.new_depth_stencil_state(&desc)
            },
            depth_texture: DepthTexture::new("Depth", DEFAULT_DEPTH_FORMAT),
            light: Camera::new(
                LIGHT_DISTANCE,
                INITIAL_LIGHT_ROTATION,
                ModifierKeys::CONTROL,
                true,
                0.,
            ),
            light_pipeline: RenderPipeline::new(
                "Light",
                &device,
                &library,
                [(DEFAULT_COLOR_FORMAT, BlendMode::NoBlend)],
                light_vertex,
                light_fragment,
                (Depth(DEFAULT_DEPTH_FORMAT), NoStencil),
            ),
            m_model_to_world,
            model,
            model_space: ModelSpace {
                m_model_to_projection: f32x4x4::identity(),
                m_normal_to_world: m_model_to_world.into(),
            },
            model_pipeline,
            needs_render: false,
            reflectivity: 0.0, // Start with pure texture, use Up arrow to add reflection
            shading_mode,
            device,
            library,
        }
    }

    #[inline]
    fn render(&mut self, render_target: &TextureRef) -> &CommandBufferRef {
        self.needs_render = false;
        let command_buffer = self
            .command_queue
            .new_command_buffer_with_unretained_references();
        command_buffer.set_label("Renderer Command Buffer");
        let depth_tx = self.depth_texture.texture();

        self.model_pipeline.new_pass(
            "Model",
            command_buffer,
            [(
                render_target,
                (0., 0., 0., 0.),
                MTLLoadAction::Clear,
                MTLStoreAction::Store,
            )],
            (depth_tx, 1., MTLLoadAction::Clear, MTLStoreAction::DontCare),
            NoStencil,
            &self.depth_state,
            MTLCullMode::Back,
            &[&HeapUsage(
                &self.model.heap,
                MTLRenderStages::Vertex | MTLRenderStages::Fragment,
            )],
            |p| {
                p.bind(
                    main_vertex_binds {
                        geometry: Bind::Skip,
                        model: Bind::Value(&self.model_space),
                    },
                    main_fragment_binds {
                        material: Bind::Skip,
                        camera: Bind::Value(&self.camera.projected_space),
                        light_pos: Bind::Value(&self.light.projected_space.position_world),
                        reflectivity: Bind::Value(&self.reflectivity),
                        env_texture: BindTexture(&self.cubemap_texture),
                    },
                );
                for draw in self.model.draws() {
                    p.debug_group(draw.name, || {
                        p.draw_primitives_with_binds(
                            main_vertex_binds {
                                geometry: Bind::buffer_with_rolling_offset(draw.geometry),
                                model: Bind::Skip,
                            },
                            main_fragment_binds {
                                material: Bind::iterating_buffer_offset(
                                    draw.geometry.1,
                                    draw.material,
                                ),
                                ..main_fragment_binds::SKIP
                            },
                            MTLPrimitiveType::Triangle,
                            0,
                            draw.vertex_count,
                        );
                    });
                }
                // BG skybox behind model
                p.into_subpass("BG", &self.bg_render_pipeline,
                    Some(&self.depth_read_only),
                    Some(MTLCullMode::None),
                    |p| {
                    p.draw_primitives_with_binds(
                        NoBinds,
                        bg_fragment_binds {
                            camera: Bind::Value(&self.camera.projected_space),
                            env_texture: BindTexture(&self.cubemap_texture),
                        },
                        MTLPrimitiveType::Triangle,
                        0,
                        3,
                    )
                });
            },
        );
        command_buffer
    }

    fn on_event(&mut self, event: UserEvent) {
        if self.camera.on_event(event) {
            self.model_space.m_model_to_projection =
                self.camera.projected_space.m_world_to_projection * self.m_model_to_world;
            self.needs_render = true;
        }
        if self.light.on_event(event) {
            self.needs_render = true;
        }
        if self.shading_mode.on_event(event) {
            self.model_pipeline =
                create_model_pipeline(&self.device, &self.library, self.shading_mode);
            self.needs_render = true;
        }
        if self.depth_texture.on_event(event, &self.device) {
            self.needs_render = true;
        }
        // Up/Down arrows: adjust reflectivity
        if let UserEvent::KeyDown { key_code, .. } = event {
            match key_code {
                // Up arrow: more reflective
                126 => {
                    self.reflectivity = (self.reflectivity + 0.05).min(1.0);
                    self.needs_render = true;
                }
                // Down arrow: less reflective
                125 => {
                    self.reflectivity = (self.reflectivity - 0.05).max(0.0);
                    self.needs_render = true;
                }
                _ => {}
            }
        }
    }

    #[inline(always)]
    fn needs_render(&self) -> bool {
        self.needs_render
    }

    fn device(&self) -> &Device {
        &self.device
    }
}

fn main() {
    launch_application::<Delegate>("Project 9 - Bedroom Environment (Up/Down: reflectivity)");
}
