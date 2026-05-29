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
    int   shader_mode;      // 0 = Blinn-Phong, 1 = PBR
    int   point_light_on;   // 0 = env light only, 1 = point light on
    int   _pad[3];
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

    // Determine shadow and lighting
    bool is_shadow = false;
    half4 tex_color;

    if (params.point_light_on) {
        // Point light mode: ray traced shadow
        const float3 to_light = normalize(light_pos.xyz - pos.xyz);
        if (dot(float3(normal), to_light) >= 0.0) {
            raytracing::ray r(pos.xyz, to_light);
            raytracing::intersector<> intersector;
            intersector.set_triangle_cull_mode(raytracing::triangle_cull_mode::back);
            intersector.assume_geometry_type(raytracing::geometry_type::triangle);
            auto intersection = intersector.intersect(r, accel_struct);
            is_shadow = intersection.type != raytracing::intersection_type::none;
        }

        if (params.shader_mode == 1) {
            TexturedMaterial mat(material, in.tx_coord, is_shadow);
            tex_color = shade_pbr(frag_pos, half3(light_pos.xyz), camera_pos, normal,
                                  half(params.metallic), half(params.roughness), mat,
                                  HasAmbient, HasDiffuse, HasSpecular);
            tex_color.rgb = tex_color.rgb / (tex_color.rgb + 1.0h);
            tex_color.rgb = powr(tex_color.rgb, half3(1.0h / 2.2h));
        } else {
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
    } else {
        // Environment light only: IBL with RT Ambient Occlusion
        constexpr sampler env_s(mag_filter::linear, address::clamp_to_zero, min_filter::linear);
        TexturedMaterial mat(material, in.tx_coord, false);
        half4 albedo = mat.diffuse_color();

        // RT Ambient Occlusion: trace rays in hemisphere around normal
        // Use a fixed set of directions for deterministic, noise-free results
        const float3 N = float3(normal);
        // Build tangent frame from normal
        float3 up = abs(N.y) < 0.99 ? float3(0,1,0) : float3(1,0,0);
        float3 T = normalize(cross(up, N));
        float3 B = cross(N, T);

        // 8 sample directions in hemisphere (cosine-weighted)
        const float ao_radius = 0.15;
        constexpr int AO_SAMPLES = 8;
        const float2 ao_dirs[AO_SAMPLES] = {
            {0.0, 0.3}, {0.7, 0.7}, {-0.5, 0.6}, {0.9, -0.1},
            {-0.8, 0.4}, {0.3, 0.9}, {-0.2, 0.8}, {0.6, -0.5}
        };
        float ao = 0.0;
        raytracing::intersector<> ao_intersector;
        ao_intersector.set_triangle_cull_mode(raytracing::triangle_cull_mode::back);
        ao_intersector.assume_geometry_type(raytracing::geometry_type::triangle);
        for (int i = 0; i < AO_SAMPLES; i++) {
            // Cosine-weighted hemisphere direction
            float x = ao_dirs[i].x;
            float z = ao_dirs[i].y;
            float y = sqrt(max(0.0, 1.0 - x*x - z*z));
            float3 dir = normalize(T * x + N * y + B * z);
            raytracing::ray r(pos.xyz + N * 0.001, dir, 0.0, ao_radius);
            auto hit = ao_intersector.intersect(r, accel_struct);
            if (hit.type != raytracing::intersection_type::none) {
                ao += 1.0;
            }
        }
        float ao_factor = 1.0 - (ao / float(AO_SAMPLES));

        // Sample environment for diffuse (use normal direction)
        half4 env_diffuse = half4(0);
        if (!is_null_texture(env_texture)) {
            env_diffuse = env_texture.sample(env_s, float3(normal));
        }

        // Sample environment for specular (use reflection direction)
        const half3 camera_dir = normalize(frag_pos - camera_pos);
        const half3 ref = reflect(camera_dir, normal);
        half4 env_spec = half4(0);
        if (!is_null_texture(env_texture)) {
            env_spec = env_texture.sample(env_s, float3(ref));
        }

        half ao_h = half(ao_factor);
        tex_color = half4(0);
        if (HasAmbient)  tex_color += mat.ambient_amount() * albedo * ao_h;
        if (HasDiffuse)  tex_color += 0.6h * albedo * env_diffuse * ao_h;
        if (HasSpecular) tex_color += 0.4h * env_spec * ao_h;
        tex_color.a = albedo.a;
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
