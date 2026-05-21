#version 330 core
in vec3 vNormal;
in vec4 vColor;
in vec3 vFragPos;

uniform float uAlpha;
uniform vec3 uLightDir;

out vec4 FragColor;

void main() {
    vec3 n = normalize(vNormal);
    float diff = max(dot(n, normalize(uLightDir)), 0.0);
    float amb = 0.3;
    vec3 color = vColor.rgb * (amb + diff * 0.7);
    // 边缘高亮
    float edge = 1.0 - abs(dot(n, vec3(0,0,1)));
    color += vec3(0.05) * edge;
    FragColor = vec4(color, vColor.a * uAlpha);
}
