#include <metal_stdlib>
#include "../../metal-shaders/src/shading.h"
#include "../../metal-types/src/geometry.h"
#include "../../metal-types/src/material.h"
#include "../../metal-types/src/model-space.h"
#include "../../metal-types/src/projected-space.h"
#include "../../metal-types/src/shading-mode.h"

using namespace metal;
using raytracing::primitive_acceleration_structure;

// ========================================
// PBR Functions
// ========================================

inline half distribution_ggx(half3 N, half3 H, half roughness) {
    half a = roughness * roughness;
    half a2 = a * a;
    half NdotH = max(dot(N, H), 0.0h);
    half denom = NdotH * NdotH * (a2 - 1.0h) + 1.0h;
    denom = M_PI_H * denom * denom;
    return a2 / max(denom, 0.0001h);
}

inline half geometry_schlick_ggx(half NdotV, half roughness) {
    half r = roughness + 1.0h;
    half k = (r * r) / 8.0h;
    return NdotV / (NdotV * (1.0h - k) + k);
}

inline half geometry_smith(half3 N, half3 V, half3 L, half roughness) {
    return geometry_schlick_ggx(max(dot(N, V), 0.0h), roughness)
         * geometry_schlick_ggx(max(dot(N, L), 0.0h), roughness);
}

inline half3 fresnel_schlick(half cosTheta, half3 F0) {
    return F0 + (1.0h - F0) * powr(saturate(1.0h - cosTheta), 5.0h);
}

template<typename T>
inline half4 shade_pbr(half3 frag_pos, half3 light_pos, half3 camera_pos, half3 N,
                       half metallic, half roughness, T material,
                       bool has_ambient, bool has_diffuse, bool has_specular) {
    const half3 V = normalize(camera_pos - frag_pos);
    const half3 L = normalize(light_pos - frag_pos);
    const half3 H = normalize(V + L);
    const half4 albedo_raw = material.diffuse_color();
    const half3 albedo = albedo_raw.rgb;

    half3 F0 = mix(half3(0.04h), albedo, metallic);
    half  NDF = distribution_ggx(N, H, roughness);
    half  G   = geometry_smith(N, V, L, roughness);
    half3 F   = fresnel_schlick(max(dot(H, V), 0.0h), F0);

    half3 spec_brdf = (NDF * G * F) / (4.0h * max(dot(N, V), 0.0h) * max(dot(N, L), 0.0h) + 0.0001h);
    half3 kD = (1.0h - F) * (1.0h - metallic);
    half NdotL = max(dot(N, L), 0.0h);
    const half light_intensity = 3.0h;

    half4 color = half4(0);
    if (has_diffuse)  color.rgb += kD * albedo / M_PI_H * NdotL * light_intensity;
    if (has_specular) color.rgb += spec_brdf * NdotL * light_intensity;
    if (has_ambient)  color.rgb += material.ambient_amount() * albedo;
    color.a = albedo_raw.a;
    return color;
}

// ========================================
// Vertex Shaders
// ========================================

struct VertexOut {
    float4 position [[position]];
    float3 normal;
    float2 tx_coord;
};

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

// ========================================
// Shader Parameters
// ========================================

struct ShaderParams {
    float reflectivity;
    float metallic;
    float roughness;
    int   shader_mode;   // 0 = Blinn-Phong, 1 = PBR
};

// ========================================
// Fragment Shader - RT Shadows + PBR/Blinn-Phong + Env Reflection
// ========================================

[[fragment]]
half4 main_fragment(         VertexOut                          in           [[stage_in]],
                    constant ProjectedSpace                   & camera       [[buffer(0)]],
                    constant float4                           & light_pos    [[buffer(1)]],
                    constant Material                         & material     [[buffer(2)]],
                    constant ShaderParams                     & params       [[buffer(3)]],
                    primitive_acceleration_structure            accel_struct  [[buffer(4)]],
                             texturecube<half>                  env_texture   [[texture(0)]]) {
    float4 pos = camera.m_screen_to_world * float4(in.position.xyz, 1);
           pos = pos / pos.w;

    const half3 frag_pos   = half3(pos.xyz);
    const half3 camera_pos = half3(camera.position_world.xyz);
    const half3 normal     = half3(normalize(in.normal));

    if (OnlyNormals) {
        return half4(normal.xy, normal.z * -1, 1);
    }

    // Ray Traced Shadow
    const float3 to_light = normalize(light_pos.xyz - pos.xyz);
    bool is_shadow = false;
    if (dot(float3(normal), to_light) >= 0.0) {
        raytracing::ray r(pos.xyz, to_light);
        raytracing::intersector<> intersector;
        intersector.set_triangle_cull_mode(raytracing::triangle_cull_mode::back);
        intersector.assume_geometry_type(raytracing::geometry_type::triangle);
        auto intersection = intersector.intersect(r, accel_struct);
        is_shadow = intersection.type != raytracing::intersection_type::none;
    }

    // Choose shading model
    half4 tex_color;
    if (params.shader_mode == 1) {
        // PBR
        TexturedMaterial mat(material, in.tx_coord, is_shadow);
        tex_color = shade_pbr(frag_pos, half3(light_pos.xyz), camera_pos, normal,
                              half(params.metallic), half(params.roughness), mat,
                              HasAmbient, HasDiffuse, HasSpecular);
        tex_color.rgb = tex_color.rgb / (tex_color.rgb + 1.0h);
        tex_color.rgb = powr(tex_color.rgb, half3(1.0h / 2.2h));
    } else {
        // Blinn-Phong
        tex_color = shade_phong_blinn(
            {
                .frag_pos     = frag_pos,
                .light_pos    = half3(light_pos.xyz),
                .camera_pos   = camera_pos,
                .normal       = normal,
                .has_ambient  = HasAmbient,
                .has_diffuse  = HasDiffuse,
                .has_specular = HasSpecular,
                .only_normals = false,
            },
            TexturedMaterial(material, in.tx_coord, is_shadow)
        );
    }

    // Environment reflection
    if (!is_null_texture(env_texture)) {
        const half3 camera_dir = normalize(frag_pos - camera_pos);
        const half3 ref = reflect(camera_dir, normal);
        constexpr sampler tx_sampler(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
        half4 env_color = env_texture.sample(tx_sampler, float3(ref));
        tex_color = mix(tex_color, env_color, half(params.reflectivity));
    }

    return tex_color;
};

// ========================================
// Light point
// ========================================

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
    return half4(1, 0.95h, 0.6h, 1); // warm yellow light
};

// ========================================
// Background Skybox
// ========================================

struct BGVertexOut { float4 position [[position]]; };

[[vertex]]
BGVertexOut bg_vertex(uint vertex_id [[vertex_id]]) {
    constexpr const float2 verts[3] = { {-1,1}, {-1,-3}, {3,1} };
    return { .position = float4(verts[vertex_id], 1, 1) };
}

[[fragment]]
half4 bg_fragment(         BGVertexOut       in          [[stage_in]],
                  constant ProjectedSpace  & camera      [[buffer(0)]],
                           texturecube<half> env_texture [[texture(0)]]) {
    constexpr sampler s(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
    return env_texture.sample(s, (camera.m_screen_to_world * float4(in.position.xy, 1, 1)).xyz);
}
