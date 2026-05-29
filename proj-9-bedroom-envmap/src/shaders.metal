#include <metal_stdlib>
#include "../../metal-shaders/src/shading.h"
#include "../../metal-types/src/geometry.h"
#include "../../metal-types/src/material.h"
#include "../../metal-types/src/model-space.h"
#include "../../metal-types/src/projected-space.h"
#include "../../metal-types/src/shading-mode.h"

using namespace metal;

struct VertexOut
{
    float4 position [[position]];
    float3 normal;
    float2 tx_coord;
};

// Shared vertex shader for model, plane, and shadow map
[[vertex]]
VertexOut main_vertex(         uint         vertex_id [[vertex_id]],
                      constant ModelSpace & model     [[buffer(0)]],
                      constant Geometry   & geometry  [[buffer(1)]]) {
    const uint idx = geometry.indices[vertex_id];
    return {
        .position = model.m_model_to_projection * float4(geometry.positions[idx], 1.0),
        .normal   = model.m_normal_to_world     * float3(geometry.normals[idx]),
        .tx_coord = geometry.tx_coords[idx]      * float2(1,-1) + float2(0,1)
    };
}

// Fragment shader with shadow + environment reflection
[[fragment]]
half4 main_fragment(         VertexOut                        in           [[stage_in]],
                    constant ProjectedSpace                 & camera       [[buffer(0)]],
                    constant ProjectedSpace                 & light        [[buffer(1)]],
                    constant Material                       & material     [[buffer(2)]],
                    constant float                          & reflectivity [[buffer(3)]],
                             depth2d<float, access::sample>   shadow_tx    [[texture(0)]],
                             texturecube<half>                 env_texture  [[texture(1)]]) {
    float4 pos = camera.m_screen_to_world * float4(in.position.xyz, 1);
           pos = pos / pos.w;

    const half3 frag_pos   = half3(pos.xyz);
    const half3 camera_pos = half3(camera.position_world.xyz);
    const half3 normal     = half3(normalize(in.normal));

    // Shadow mapping
    float4 pos_light = light.m_world_to_projection * pos;
           pos_light = pos_light / pos_light.w;

    constexpr sampler shadow_sampler(address::clamp_to_border,
                                     border_color::opaque_white,
                                     compare_func::less_equal,
                                     filter::linear);
    const bool is_shadow = is_null_texture(shadow_tx)
                                ? false
                                : shadow_tx.sample_compare(shadow_sampler, pos_light.xy, pos_light.z) < 1;

    // Texture-based shading with shadow
    half4 tex_color = shade_phong_blinn(
        {
            .frag_pos     = frag_pos,
            .light_pos    = half3(light.position_world.xyz),
            .camera_pos   = camera_pos,
            .normal       = normal,
            .has_ambient  = HasAmbient,
            .has_diffuse  = HasDiffuse,
            .has_specular = HasSpecular,
            .only_normals = OnlyNormals,
        },
        TexturedMaterial(material, in.tx_coord, is_shadow)
    );

    // Environment reflection (only if cubemap is bound)
    if (!is_null_texture(env_texture)) {
        const half3 camera_dir = normalize(frag_pos - camera_pos);
        const half3 ref = reflect(camera_dir, normal);
        constexpr sampler tx_sampler(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
        half4 env_color = env_texture.sample(tx_sampler, float3(ref));
        tex_color = mix(tex_color, env_color, half(reflectivity));
    }

    return tex_color;
};

// Background skybox
struct BGVertexOut {
    float4 position [[position]];
};

[[vertex]]
BGVertexOut bg_vertex(uint vertex_id [[vertex_id]]) {
    constexpr const float2 plane_triange_strip_vertices[3] = {
        {-1.h,  1.h},
        {-1.h, -3.h},
        { 3.h,  1.h},
    };
    const float2 position2d = plane_triange_strip_vertices[vertex_id];
    return { .position = float4(position2d, 1, 1) };
}

[[fragment]]
half4 bg_fragment(         BGVertexOut         in          [[stage_in]],
                  constant ProjectedSpace    & camera      [[buffer(0)]],
                           texturecube<half>   env_texture [[texture(0)]]) {
    constexpr sampler tx_sampler(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
    const float4 pos   = camera.m_screen_to_world * float4(in.position.xy, 1, 1);
    const half4  color = env_texture.sample(tx_sampler, pos.xyz);
    return color;
}
