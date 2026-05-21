#pragma once

#include <QMatrix4x4>
#include <QVector3D>
#include <QQuaternion>

// Arcball 相机：鼠标左键旋转，右键平移，滚轮缩放
class Camera {
public:
    Camera();

    void setTarget(const QVector3D& target);
    void setDistance(float d);
    void setViewport(int w, int h);

    // 交互
    void rotate(const QPointF& delta);      // 屏幕像素差 → 旋转
    void pan(const QPointF& delta);         // 屏幕像素差 → 平移
    void zoom(float delta);                 // 滚轮 → 缩放

    QMatrix4x4 viewMatrix() const;
    QMatrix4x4 projectionMatrix() const;
    QVector3D position() const;

    float distance() const { return m_dist; }

private:
    QVector3D m_target{0, 0, 0};
    float m_dist = 10.0f;
    QQuaternion m_rot;
    int m_width = 800;
    int m_height = 600;
    float m_fov = 45.0f;
    float m_near = 0.01f;
    float m_far = 1000.0f;
};
