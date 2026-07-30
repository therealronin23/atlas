#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float uTime;
    vec2 uSize;
};

void main() {
    vec2 center = vec2(0.5, 0.5);
    vec2 p = (qt_TexCoord0 - center) * uSize;
    float dist = length(p);
    float maxRadius = min(uSize.x, uSize.y) * 0.4;

    float ring1 = abs(dist - maxRadius * (0.5 + 0.1 * sin(uTime * 1.3)));
    float ring2 = abs(dist - maxRadius * (0.8 + 0.08 * sin(uTime * 1.7 + 1.0)));
    float ring3 = abs(dist - maxRadius * (0.65 + 0.12 * sin(uTime * 0.9 + 2.4)));

    float glow1 = smoothstep(24.0, 0.0, ring1);
    float glow2 = smoothstep(18.0, 0.0, ring2);
    float glow3 = smoothstep(20.0, 0.0, ring3);

    float alpha = clamp(glow1 * 0.8 + glow2 * 0.5 + glow3 * 0.6, 0.0, 1.0);
    vec3 cyan = vec3(0.0, 0.85, 1.0);
    vec3 violet = vec3(0.6, 0.2, 1.0);
    vec3 color = cyan * (glow1 * 0.8 + glow2 * 0.5) + violet * (glow3 * 0.6);
    fragColor = vec4(color, alpha) * qt_Opacity;
}
