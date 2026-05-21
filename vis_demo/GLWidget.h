#pragma once

#include "Camera.h"
#include "SceneBuilder.h"
#include <QOpenGLWidget>
#include <QOpenGLFunctions_3_3_Core>
#include <QOpenGLShaderProgram>

struct GLBatch {
    unsigned int vao = 0, vbo = 0, nbo = 0, cbo = 0, ebo = 0;
    int indexCount = 0;
    int vertCount = 0;
    bool hasNormals = false;
    bool hasIndices = false;
};

class GLWidget : public QOpenGLWidget, protected QOpenGLFunctions_3_3_Core {
    Q_OBJECT
public:
    explicit GLWidget(QWidget* parent = nullptr);
    ~GLWidget() override;

    void setScene(SceneData scene);
    void resetCamera();

protected:
    void initializeGL() override;
    void resizeGL(int w, int h) override;
    void paintGL() override;

    void mousePressEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    void mouseMoveEvent(QMouseEvent* e) override;
    void wheelEvent(QWheelEvent* e) override;

private:
    void uploadBatches();
    GLBatch doUploadLine(const DrawBatch& b);
    GLBatch doUploadTri(const DrawBatch& b);

    Camera m_cam;
    SceneData m_scene;
    bool m_dirty = true;

    QOpenGLShaderProgram* m_phongProg = nullptr;
    QOpenGLShaderProgram* m_lineProg = nullptr;

    std::vector<GLBatch> m_glBatches;
    std::vector<GLBatch> m_glTracks;
    std::vector<GLBatch> m_glHits;
    GLBatch m_glBeam;

    QPoint m_lastMouse;
    bool m_leftDown = false;
    bool m_rightDown = false;
    bool m_middleDown = false;

    bool m_glReady = false;
};
