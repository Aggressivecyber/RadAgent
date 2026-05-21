#include "Camera.h"
#include <cmath>

Camera::Camera() {
    m_rot = QQuaternion::fromRotationMatrix(
        QMatrix4x4(1,0,0,0, 0,0,-1,0, 0,1,0,0, 0,0,0,1).toGenericMatrix<3,3>()
    );
}

void Camera::setTarget(const QVector3D& t) { m_target = t; }
void Camera::setDistance(float d) { m_dist = std::max(0.1f, d); }
void Camera::setViewport(int w, int h) { m_width = w; m_height = h; }

void Camera::rotate(const QPointF& delta) {
    float ax = float(delta.y()) * 0.5f;
    float ay = float(delta.x()) * 0.5f;
    auto qx = QQuaternion::fromAxisAndAngle(QVector3D(1,0,0), ax);
    auto qy = QQuaternion::fromAxisAndAngle(QVector3D(0,1,0), ay);
    m_rot = qy * qx * m_rot;
    m_rot.normalize();
}

void Camera::pan(const QPointF& delta) {
    float scale = m_dist * 0.002f;
    auto right = m_rot.rotatedVector(QVector3D(1,0,0));
    auto up    = m_rot.rotatedVector(QVector3D(0,1,0));
    m_target -= right * float(delta.x()) * scale;
    m_target += up * float(delta.y()) * scale;
}

void Camera::zoom(float delta) {
    m_dist *= std::pow(0.95f, delta);
    m_dist = std::max(0.1f, std::min(m_dist, 500.0f));
}

QMatrix4x4 Camera::viewMatrix() const {
    auto pos = position();
    auto up  = m_rot.rotatedVector(QVector3D(0,1,0));
    QMatrix4x4 m;
    m.lookAt(pos, m_target, up);
    return m;
}

QMatrix4x4 Camera::projectionMatrix() const {
    QMatrix4x4 m;
    m.perspective(m_fov, float(m_width) / std::max(1, m_height), m_near, m_far);
    return m;
}

QVector3D Camera::position() const {
    return m_target + m_rot.rotatedVector(QVector3D(0, 0, m_dist));
}
