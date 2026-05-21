#include "SceneBuilder.h"
#include <cmath>
#include <algorithm>

static void addBox(DrawBatch& b,
                   float cx, float cy, float cz,
                   float sx, float sy, float sz,
                   float r, float g, float bl, float a)
{
    float hx = sx/2, hy = sy/2, hz = sz/2;
    unsigned int base = (unsigned int)(b.vertices.size() / 3);

    // 6 faces, 4 verts each
    float verts[][3] = {
        {cx-hx,cy-hy,cz+hz},{cx+hx,cy-hy,cz+hz},{cx+hx,cy+hy,cz+hz},{cx-hx,cy+hy,cz+hz},  // front
        {cx+hx,cy-hy,cz-hz},{cx-hx,cy-hy,cz-hz},{cx-hx,cy+hy,cz-hz},{cx+hx,cy+hy,cz-hz},  // back
        {cx-hx,cy+hy,cz-hz},{cx-hx,cy+hy,cz+hz},{cx+hx,cy+hy,cz+hz},{cx+hx,cy+hy,cz-hz},  // top
        {cx-hx,cy-hy,cz+hz},{cx-hx,cy-hy,cz-hz},{cx+hx,cy-hy,cz-hz},{cx+hx,cy-hy,cz+hz},  // bottom
        {cx+hx,cy-hy,cz+hz},{cx+hx,cy-hy,cz-hz},{cx+hx,cy+hy,cz-hz},{cx+hx,cy+hy,cz+hz},  // right
        {cx-hx,cy-hy,cz-hz},{cx-hx,cy-hy,cz+hz},{cx-hx,cy+hy,cz+hz},{cx-hx,cy+hy,cz-hz},  // left
    };
    float norms[][3] = {
        {0,0,1},{0,0,-1},{0,1,0},{0,-1,0},{1,0,0},{-1,0,0}
    };
    // 每面 6 个 index（2 个三角形）
    for (int f = 0; f < 6; f++) {
        for (int v = 0; v < 4; v++) {
            b.vertices.insert(b.vertices.end(), verts[f*4+v], verts[f*4+v]+3);
            b.normals.insert(b.normals.end(), norms[f], norms[f]+3);
            b.colors.insert(b.colors.end(), {r, g, bl, a});
        }
        unsigned int o = base + f*4;
        b.indices.insert(b.indices.end(), {o,o+1,o+2, o,o+2,o+3});
    }
}

static void addArrow(DrawBatch& b,
                     float x0, float y0, float z0,
                     float x1, float y1, float z1,
                     float r, float g, float bl, float a,
                     float shaftWidth = 0.3f)
{
    // 简单箭头用线段
    b.vertices.insert(b.vertices.end(), {x0,y0,z0});
    b.colors.insert(b.colors.end(), {r,g,bl,a});
    b.vertices.insert(b.vertices.end(), {x1,y1,z1});
    b.colors.insert(b.colors.end(), {r,g,bl,a});
    b.wireframe = true;
    b.lineWidth = 3.0f;

    // 箭头尖端（锥形指示，用 4 条短线）
    float dx = x1-x0, dy = y1-y0, dz = z1-z0;
    float len = std::sqrt(dx*dx+dy*dy+dz*dz);
    if (len < 0.001f) return;
    dx/=len; dy/=len; dz/=len;
    float tipLen = std::min(2.0f, len * 0.15f);
    // 任意垂直方向
    float px,py,pz;
    if (std::abs(dy) < 0.9f) { px=-dy; py=dx; pz=0; }
    else { px=0; py=-dz; pz=dy; }
    float pl = std::sqrt(px*px+py*py+pz*pz);
    px/=pl; py/=pl; pz/=pl;
    float w = shaftWidth;

    float tx = x1-dx*tipLen, ty = y1-dy*tipLen, tz = z1-dz*tipLen;
    for (int i = 0; i < 4; i++) {
        float angle = i * M_PI / 2.0f;
        float qx = px*std::cos(angle) + (dy*pz-dz*py)*std::sin(angle);
        float qy = py*std::cos(angle) + (dz*px-dx*pz)*std::sin(angle);
        float qz = pz*std::cos(angle) + (dx*py-dy*px)*std::sin(angle);
        b.vertices.insert(b.vertices.end(), {x1,y1,z1});
        b.colors.insert(b.colors.end(), {r,g,bl,a});
        b.vertices.insert(b.vertices.end(), {tx+qx*w, ty+qy*w, tz+qz*w});
        b.colors.insert(b.colors.end(), {r,g,bl,a});
    }
}

SceneData buildScene(const SimData& sim) {
    SceneData scene;

    float halfWorld = sim.worldSize / 2.0f;

    // 1. 计算每层 Z 位置（从上往下排列）
    float totalThickness = 0;
    for (auto& l : sim.layers) totalThickness += l.thickness;
    float startZ = totalThickness / 2.0f;

    // 2. 构建屏蔽层几何体
    float curZ = startZ;
    for (auto& layer : sim.layers) {
        DrawBatch batch;
        batch.alpha = 0.6f;
        float cx = 0, cy = 0;
        float cz = curZ - layer.thickness / 2.0f;
        float sx = halfWorld, sy = halfWorld;
        float sz = layer.thickness;
        addBox(batch, cx, cy, cz, sx, sy, sz,
               layer.color.x(), layer.color.y(), layer.color.z(), 0.6f);
        scene.batches.push_back(std::move(batch));

        // 线框版本（边缘高亮）
        DrawBatch wire;
        wire.wireframe = true;
        wire.lineWidth = 1.5f;
        addBox(wire, cx, cy, cz, sx, sy, sz,
               layer.color.x()*1.2f, layer.color.y()*1.2f, layer.color.z()*1.2f, 0.8f);
        scene.batches.push_back(std::move(wire));

        curZ -= layer.thickness;
    }

    // 3. 世界边界框
    {
        DrawBatch wire;
        wire.wireframe = true;
        wire.lineWidth = 1.0f;
        addBox(wire, 0,0,0, sim.worldSize, sim.worldSize, sim.worldSize,
               0.4f, 0.4f, 0.4f, 0.3f);
        scene.batches.push_back(std::move(wire));
    }

    // 4. 入射粒子箭头
    {
        DrawBatch arrow;
        float zStart = startZ + 5.0f;
        addArrow(arrow,
                 sim.beamX, sim.beamY, zStart,
                 sim.beamX, sim.beamY, startZ,
                 1.0f, 1.0f, 0.0f, 1.0f, 0.3f);
        scene.beamArrow = std::move(arrow);
    }

    // 5. 粒子轨迹
    for (auto& track : sim.tracks) {
        if (track.points.size() < 2) continue;
        DrawBatch line;
        line.wireframe = true;
        line.lineWidth = 2.0f;
        for (auto& pt : track.points) {
            line.vertices.insert(line.vertices.end(), {pt.pos.x(), pt.pos.y(), pt.pos.z()});
            float alpha = 1.0f - pt.kineticEnergy / std::max(0.001f, track.initialEnergy);
            alpha = std::max(0.3f, std::min(1.0f, alpha));
            line.colors.insert(line.colors.end(),
                {float(track.color.redF()), float(track.color.greenF()),
                 float(track.color.blueF()), alpha});
        }
        scene.trackLines.push_back(std::move(line));
    }

    // 6. 碰撞点（能量沉积 > 0 的步长终点）
    {
        DrawBatch points;
        points.wireframe = true;
        points.lineWidth = 6.0f;
        for (auto& hit : sim.hits) {
            points.vertices.insert(points.vertices.end(),
                {hit.pos.x(), hit.pos.y(), hit.pos.z()});
            float intensity = std::min(1.0f, hit.edep / 5.0f);
            points.colors.insert(points.colors.end(),
                {1.0f, 1.0f-intensity, 0.2f, 0.9f});
        }
        scene.hitPoints.push_back(std::move(points));
    }

    // 计算场景半径
    scene.sceneRadius = std::max(sim.worldSize, totalThickness + 10.0f);
    return scene;
}
