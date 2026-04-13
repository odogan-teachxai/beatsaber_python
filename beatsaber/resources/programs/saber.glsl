#version 330

#if defined VERTEX_SHADER

in vec3 in_position;

uniform mat4 m_proj;
uniform mat4 m_cam;
uniform vec3 position;      // Hand position in world space
uniform float rotation;     // Rotation angle in radians
uniform float length;       // Saber length

out vec3 v_pos;

void main() {
    // Create rotation matrix around Z axis
    float c = cos(rotation);
    float s = sin(rotation);
    mat3 rot = mat3(
        c, -s, 0.0,
        s, c, 0.0,
        0.0, 0.0, 1.0
    );

    // Scale the saber (thin cylinder, length along Y)
    vec3 scaled = vec3(in_position.x * 0.1, in_position.y * length, in_position.z * 0.1);

    // Rotate and translate to hand position
    vec3 world_pos = rot * scaled + position;

    vec4 p = m_cam * vec4(world_pos, 1.0);
    gl_Position = m_proj * p;
    v_pos = p.xyz;
}

#elif defined FRAGMENT_SHADER

out vec4 fragColor;
uniform vec4 color;

in vec3 v_pos;

void main()
{
    // Simple glow effect - brighter at edges
    float dist = length(v_pos);
    float glow = 1.0 - smoothstep(0.0, 50.0, dist) * 0.3;
    fragColor = color * glow;
}

#endif
