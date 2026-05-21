#pragma once

#include <QString>
#include <QVector3D>
#include <QColor>
#include <vector>
#include <map>

// 粒子轨迹：一系列带位置和能量沉积的步长点
struct TrackPoint {
    QVector3D pos;
    float edep = 0;          // MeV
    float kineticEnergy = 0; // MeV
};

struct Track {
    int eventId = 0;
    int trackId = 0;
    int parentId = 0;
    QString particle;
    float initialEnergy = 0;  // MeV
    QColor color;
    std::vector<TrackPoint> points;
};

// 屏蔽层
struct ShieldLayer {
    QString material;
    float thickness;       // cm
    float density;         // g/cm3
    QVector3D color;       // 渲染颜色
};

// 碰撞点
struct HitPoint {
    QVector3D pos;
    float edep;
    QString particle;
    int eventId;
};

// 仿真数据
struct SimData {
    float worldSize = 50.0f;        // cm
    float beamX = 0, beamY = 0;     // 粒子入射位置
    float beamZ = 0;                // 起始Z
    float beamDirX = 0, beamDirY = 0, beamDirZ = -1;  // 入射方向
    float beamEnergy = 100;         // MeV
    std::vector<ShieldLayer> layers;
    std::vector<Track> tracks;
    std::vector<HitPoint> hits;
};

// 粒子颜色映射
QColor particleColor(const QString& name);
