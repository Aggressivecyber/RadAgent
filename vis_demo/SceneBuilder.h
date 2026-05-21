#pragma once

#include "ParticleData.h"
#include <vector>

// OpenGL 绘制数据（借鉴 tools/sg 的 separator/matrix/vertices/rgba 思路）
struct DrawBatch {
    std::vector<float> vertices;   // x,y,z
    std::vector<float> normals;    // nx,ny,nz
    std::vector<float> colors;     // r,g,b,a
    std::vector<unsigned int> indices;
    bool wireframe = false;
    float lineWidth = 1.0f;
    float alpha = 1.0f;
};

struct SceneData {
    std::vector<DrawBatch> batches;
    // 轨迹线（line_strip，不需要 index）
    std::vector<DrawBatch> trackLines;
    // 碰撞点（points）
    std::vector<DrawBatch> hitPoints;
    // 入射箭头
    DrawBatch beamArrow;
    // 场景边界
    float sceneRadius = 50;
};

// 从 SimData 构建场景
SceneData buildScene(const SimData& sim);
