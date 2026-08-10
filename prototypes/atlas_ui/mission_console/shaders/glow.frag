#version 460 core

#include <flutter/runtime_effect.glsl>

precision mediump float;

uniform vec2 uSize;
uniform float uTime;

out vec4 fragColor;

// Glow radial en torno a `radius`, mismo comportamiento que el anillo
// original: brillo alto cerca del radio, cae a 0 hacia fuera.
float ringGlow(float dist, float radius) {
    float glow = radius / (dist + 0.02);
    return clamp(glow - 1.0, 0.0, 3.0);
}

void main() {
    vec2 uv = FlutterFragCoord() / uSize;
    vec2 center = vec2(0.5, 0.5);
    float dist = distance(uv, center);

    // Anillo exterior — más grande, pulso lento (fase 0).
    float pulseOuter = 0.5 + 0.5 * sin(uTime * 1.5);
    float radiusOuter = 0.30 + 0.06 * pulseOuter;
    float glowOuter = ringGlow(dist, radiusOuter);

    // Anillo interior — más pequeño, pulso más rápido y desfasado.
    float pulseInner = 0.5 + 0.5 * sin(uTime * 2.6 + 3.14159);
    float radiusInner = 0.13 + 0.035 * pulseInner;
    float glowInner = ringGlow(dist, radiusInner);

    vec3 cyan = vec3(0.15, 0.85, 0.95);
    vec3 magenta = vec3(0.85, 0.30, 0.95);

    vec3 color = cyan * glowOuter + magenta * glowInner;
    float alpha = clamp(glowOuter + glowInner, 0.0, 1.0);

    fragColor = vec4(color, alpha);
}
