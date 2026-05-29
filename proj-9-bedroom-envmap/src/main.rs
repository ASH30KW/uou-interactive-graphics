#![feature(generic_associated_types)]
#![feature(portable_simd)]
mod shader_bindings;

use metal_app::{
    components::{Camera, DepthTexture, ShadingModeSelector},
    metal::*,
    metal_types::*,
    model_acceleration_structure::ModelAccelerationStructure,
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

const DEFAULT_AMBIENT_AMOUNT: u32 = 15;
const INITIAL_CAMERA_ROTATION: f32x2 = f32x2::from_array([-PI / 6., 0.]);
const INITIAL_LIGHT_ROTATION: f32x2 = f32x2::from_array([-PI / 5., PI / 16.]);
const LIBRARY_BYTES: &'static [u8] = include_bytes!(concat!(env!("OUT_DIR"), "/shaders.metallib"));
const USAGE_RENDER_STAGES: MTLRenderStages = unsafe {
    MTLRenderStages::from_bits_unchecked(
        MTLRenderStages::Vertex.bits() | MTLRenderStages::Fragment.bits(),
    )
};

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ShaderParams {
    reflectivity: f32,
    metallic: f32,
    roughness: f32,
    shader_mode: i32,
}

struct ModelInstance {
    m_model_to_world: f32x4x4,
    model: Model<Geometry, HasMaterial<Material>>,
    model_space: ModelSpace,
    name: &'static str,
}

impl ModelInstance {
    #[inline]
    fn new<const AMBIENT_AMOUNT: u32>(
        name: &'static str,
        device: &Device,
        model_file: PathBuf,
        init_m: impl FnOnce(&MaxBounds) -> f32x4x4,
    ) -> Self {
        let model = Model::from_file(
            model_file, device,
            |arg: &mut Geometry, geo| {
                arg.indices = geo.indices_buffer;
                arg.positions = geo.positions_buffer;
                arg.normals = geo.normals_buffer;
                arg.tx_coords = geo.tx_coords_buffer;
            },
            HasMaterial(|arg: &mut Material, mat: MaterialToEncode| {
                arg.ambient_texture = mat.ambient_texture;
                arg.diffuse_texture = mat.diffuse_texture;
                arg.specular_texture = mat.specular_texture;
                arg.specular_shineness = mat.specular_shineness;
                arg.ambient_amount = (AMBIENT_AMOUNT as f32) / 100.;
            }),
        );
        Self {
            m_model_to_world: init_m(&model.geometry_max_bounds),
            model, model_space: ModelSpace::default(), name,
        }
    }

    fn on_camera_update(&mut self, m_world_to_proj: f32x4x4) {
        self.model_space = ModelSpace {
            m_model_to_projection: m_world_to_proj * self.m_model_to_world,
            m_normal_to_world: self.m_model_to_world.into(),
        };
    }
}

struct Delegate {
    bg_pipeline: RenderPipeline<1, bg_vertex, bg_fragment, (Depth, NoStencil)>,
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
    model: ModelInstance,
    model_as: ModelAccelerationStructure,
    model_light: ModelInstance,
    model_plane: ModelInstance,
    model_pipeline: RenderPipeline<1, main_vertex, main_fragment, (Depth, NoStencil)>,
    needs_render: bool,
    shader_params: ShaderParams,
    shading_mode: ShadingModeSelector,
}

fn create_pipeline(
    device: &Device, library: &Library, shading_mode: ShadingModeSelector,
) -> RenderPipeline<1, main_vertex, main_fragment, (Depth, NoStencil)> {
    RenderPipeline::new(
        "Model", device, library,
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

        let library = device
            .new_library_with_data(LIBRARY_BYTES)
            .expect("Failed to import shader metal lib.");
        let command_queue = device.new_command_queue();

        let assets_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..").join("common-assets");
        let chair_path = assets_dir.join("chair").join("chair.obj");

        let mut plane_y = 0_f32;
        let mut m_model_to_world = f32x4x4::identity();
        let shading_mode = ShadingModeSelector::DEFAULT;

        let model = ModelInstance::new::<DEFAULT_AMBIENT_AMOUNT>(
            "Chair", &device, chair_path.clone(),
            |&MaxBounds { center, size }| {
                let &[cx, cy, cz, _] = center.neg().as_array();
                let scale = 1. / size.reduce_max();
                plane_y = 0.5 * scale * size[2];
                m_model_to_world = (f32x4x4::scale(scale, scale, scale, 1.)
                    * (f32x4x4::y_rotate(PI) * f32x4x4::x_rotate(PI / 2.)))
                    * f32x4x4::translate(cx, cy, cz);
                m_model_to_world
            },
        );

        let model_as = ModelAccelerationStructure::from_file(
            &chair_path, &device, &command_queue,
            |_, _| m_model_to_world,
        );

        Self {
            bg_pipeline: RenderPipeline::new(
                "BG", &device, &library,
                [(DEFAULT_COLOR_FORMAT, BlendMode::NoBlend)],
                bg_vertex, bg_fragment,
                (Depth(DEFAULT_DEPTH_FORMAT), NoStencil),
            ),
            camera: Camera::new_with_default_distance(
                INITIAL_CAMERA_ROTATION, ModifierKeys::empty(), false, 0.,
            ),
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
            light: Camera::new_with_default_distance(
                INITIAL_LIGHT_ROTATION, ModifierKeys::CONTROL, true, 1.,
            ),
            light_pipeline: RenderPipeline::new(
                "Light", &device, &library,
                [(DEFAULT_COLOR_FORMAT, BlendMode::NoBlend)],
                light_vertex, light_fragment,
                (Depth(DEFAULT_DEPTH_FORMAT), NoStencil),
            ),
            model,
            model_as,
            model_light: ModelInstance::new::<80>(
                "Light", &device,
                assets_dir.join("light").join("light.obj"),
                |_| f32x4x4::identity(),
            ),
            model_plane: ModelInstance::new::<DEFAULT_AMBIENT_AMOUNT>(
                "Plane", &device,
                assets_dir.join("plane").join("plane.obj"),
                |_| f32x4x4::translate(0., -plane_y, 0.),
            ),
            model_pipeline: create_pipeline(&device, &library, shading_mode),
            needs_render: true,
            shader_params: ShaderParams {
                reflectivity: 0.15,
                metallic: 0.0,
                roughness: 0.3,
                shader_mode: 0,
            },
            shading_mode,
            library,
            device,
            command_queue,
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
            "Scene",
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
            MTLCullMode::None,
            &[
                &HeapUsage(&self.model.model.heap, USAGE_RENDER_STAGES),
                &HeapUsage(&self.model_plane.model.heap, USAGE_RENDER_STAGES),
                &HeapUsage(&self.model_light.model.heap, USAGE_RENDER_STAGES),
            ],
            |p| {
                p.bind(
                    main_vertex_binds::SKIP,
                    main_fragment_binds {
                        camera: Bind::Value(&self.camera.projected_space),
                        light_pos: Bind::Value(&self.light.projected_space.position_world),
                        params: Bind::Value(&self.shader_params),
                        accel_struct: self.model_as.bind(),
                        env_texture: BindTexture(&self.cubemap_texture),
                        ..Binds::SKIP
                    },
                );
                // Render light model, chair, plane
                for m in [&self.model_light, &self.model, &self.model_plane] {
                    p.debug_group(m.name, || {
                        p.bind(
                            main_vertex_binds {
                                model: Bind::Value(&m.model_space),
                                ..Binds::SKIP
                            },
                            Binds::SKIP,
                        );
                        for draw in m.model.draws() {
                            p.draw_primitives_with_binds(
                                main_vertex_binds {
                                    geometry: Bind::buffer_with_rolling_offset(draw.geometry),
                                    ..Binds::SKIP
                                },
                                main_fragment_binds {
                                    material: Bind::iterating_buffer_offset(
                                        draw.geometry.1,
                                        draw.material,
                                    ),
                                    ..Binds::SKIP
                                },
                                MTLPrimitiveType::Triangle,
                                0,
                                draw.vertex_count,
                            );
                        }
                    });
                }
                // BG skybox
                p.into_subpass("BG", &self.bg_pipeline,
                    Some(&self.depth_read_only),
                    Some(MTLCullMode::None),
                    |p| {
                    p.draw_primitives_with_binds(
                        NoBinds,
                        bg_fragment_binds {
                            camera: Bind::Value(&self.camera.projected_space),
                            env_texture: BindTexture(&self.cubemap_texture),
                        },
                        MTLPrimitiveType::Triangle, 0, 3,
                    )
                });
            },
        );
        command_buffer
    }

    #[inline]
    fn on_event(&mut self, event: UserEvent) {
        if self.camera.on_event(event) {
            for m in [&mut self.model, &mut self.model_plane, &mut self.model_light] {
                m.on_camera_update(self.camera.projected_space.m_world_to_projection);
            }
            self.needs_render = true;
        }
        if self.light.on_event(event) {
            // Update light model position
            self.model_light.m_model_to_world = self.light.get_camera_to_world_transform()
                * f32x4x4::y_rotate(PI)
                * f32x4x4::scale(0.1, 0.1, 0.1, 1.0);
            self.model_light
                .on_camera_update(self.camera.projected_space.m_world_to_projection);
            self.needs_render = true;
        }
        if self.shading_mode.on_event(event) {
            self.model_pipeline =
                create_pipeline(&self.device, &self.library, self.shading_mode);
            self.needs_render = true;
        }
        if self.depth_texture.on_event(event, &self.device) {
            self.needs_render = true;
        }
        if let UserEvent::KeyDown { key_code, .. } = event {
            match key_code {
                126 => { self.shader_params.reflectivity = (self.shader_params.reflectivity + 0.05).min(1.0); self.needs_render = true; }
                125 => { self.shader_params.reflectivity = (self.shader_params.reflectivity - 0.05).max(0.0); self.needs_render = true; }
                35 => { self.shader_params.shader_mode = if self.shader_params.shader_mode == 0 { 1 } else { 0 }; self.needs_render = true; }
                123 => { self.shader_params.roughness = (self.shader_params.roughness - 0.05).max(0.05); self.needs_render = true; }
                124 => { self.shader_params.roughness = (self.shader_params.roughness + 0.05).min(1.0); self.needs_render = true; }
                46 => { self.shader_params.metallic = if self.shader_params.metallic < 0.5 { 1.0 } else { 0.0 }; self.needs_render = true; }
                _ => {}
            }
        }
    }

    #[inline(always)]
    fn needs_render(&self) -> bool { self.needs_render }

    #[inline]
    fn device(&self) -> &Device { &self.device }
}

fn main() {
    launch_application::<Delegate>("Project 9 - Bedroom (P:shader M:metal Arrows:rough/reflect Ctrl+Drag:light)");
}
