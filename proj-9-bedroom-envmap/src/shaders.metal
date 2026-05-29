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

// Main model vertex shader - with texture coordinates
[[vertex]]
VertexOut main_vertex(         uint         vertex_id [[vertex_id]],
                      constant Geometry   & geometry  [[buffer(0)]],
                      constant ModelSpace & model     [[buffer(1)]]) {
    const uint   idx      = geometry.indices[vertex_id];
    const float4 position = float4(geometry.positions[idx], 1.0);
    const float3 normal   = geometry.normals[idx];
    const float2 tx_coord = geometry.tx_coords[idx];
    return {
        .position  = model.m_model_to_projection * position,
        .normal    = model.m_normal_to_world * normal,
        .tx_coord  = float2(tx_coord.x, 1. - tx_coord.y)
    };
}

// Main model fragment shader - texture + environment reflection blend
[[fragment]]
half4 main_fragment(         VertexOut           in          [[stage_in]],
                    constant Material          & material    [[buffer(0)]],
                    constant ProjectedSpace    & camera      [[buffer(1)]],
                    constant float4            & light_pos   [[buffer(2)]],
                    constant float             & reflectivity [[buffer(3)]],
                             texturecube<half>   env_texture  [[texture(0)]]) {
    // World position from screen
    float4 pos = camera.m_screen_to_world * float4(in.position.xyz, 1);
           pos = pos / pos.w;

    const half3 frag_pos   = half3(pos.xyz);
    const half3 camera_pos = half3(camera.position_world.xyz);
    const half3 camera_dir = normalize(frag_pos - camera_pos);
    const half3 normal     = half3(normalize(in.normal));

    // Texture-based shading (Phong-Blinn)
    half4 tex_color = shade_phong_blinn(
        {
            .frag_pos     = frag_pos,
            .light_pos    = half3(light_pos.xyz),
            .camera_pos   = camera_pos,
            .normal       = normal,
            .has_ambient  = HasAmbient,
            .has_diffuse  = HasDiffuse,
            .has_specular = HasSpecular,
            .only_normals = OnlyNormals,
        },
        TexturedMaterial(material, in.tx_coord)
    );

    // Environment reflection
    const half3 ref = reflect(camera_dir, normal);
    constexpr sampler tx_sampler(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
    half4 env_color = env_texture.sample(tx_sampler, float3(ref));

    // Blend texture and environment reflection
    return mix(tex_color, env_color, half(reflectivity));
};

// Light point
struct LightVertexOut {
    float4 position [[position]];
    float  size     [[point_size]];
};

[[vertex]]
LightVertexOut light_vertex(constant ProjectedSpace & camera    [[buffer(0)]],
                            constant float4         & light_pos [[buffer(1)]]) {
    return {
        .position = camera.m_world_to_projection * light_pos,
        .size = 50,
    };
}

[[fragment]]
half4 light_fragment(const float2 point_coord [[point_coord]]) {
    half dist_from_center = length(half2(point_coord) - 0.5h);
    if (dist_from_center > 0.5) discard_fragment();
    return half4(1);
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
