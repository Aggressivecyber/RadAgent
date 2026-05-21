#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec4 aColor;

uniform mat4 uMVP;
uniform mat4 uModel;

out vec3 vNormal;
out vec4 vColor;
out vec3 vFragPos;

void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vFragPos = (uModel * vec4(aPos, 1.0)).xyz;
    vNormal = mat3(transpose(inverse(uModel))) * aNormal;
    vColor = aColor;
}
