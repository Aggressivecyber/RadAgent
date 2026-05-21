#include "GLWidget.h"
#include <QMouseEvent>
#include <QWheelEvent>
#include <QFile>
#include <QDebug>

GLWidget::GLWidget(QWidget* parent) : QOpenGLWidget(parent) {
    setFocusPolicy(Qt::StrongFocus);
    setMinimumSize(600, 400);
}

GLWidget::~GLWidget() {
    makeCurrent();
    for (auto& b : m_glBatches) { glDeleteVertexArrays(1,&b.vao); glDeleteBuffers(1,&b.vbo); glDeleteBuffers(1,&b.ebo); glDeleteBuffers(1,&b.nbo); glDeleteBuffers(1,&b.cbo); }
    for (auto& b : m_glTracks) { glDeleteVertexArrays(1,&b.vao); glDeleteBuffers(1,&b.vbo); glDeleteBuffers(1,&b.cbo); }
    for (auto& b : m_glHits)   { glDeleteVertexArrays(1,&b.vao); glDeleteBuffers(1,&b.vbo); glDeleteBuffers(1,&b.cbo); }
    { auto& b = m_glBeam; glDeleteVertexArrays(1,&b.vao); glDeleteBuffers(1,&b.vbo); glDeleteBuffers(1,&b.cbo); }
    delete m_phongProg;
    delete m_lineProg;
    doneCurrent();
}

void GLWidget::setScene(SceneData scene) {
    m_scene = std::move(scene);
    m_dirty = true;
    m_cam.setDistance(m_scene.sceneRadius * 1.8f);
    m_cam.setTarget({0, 0, 0});
    if (m_glReady) { makeCurrent(); uploadBatches(); doneCurrent(); }
    update();
}

void GLWidget::resetCamera() {
    m_cam.setDistance(m_scene.sceneRadius * 1.8f);
    m_cam.setTarget({0, 0, 0});
    update();
}

void GLWidget::initializeGL() {
    initializeOpenGLFunctions();
    glClearColor(0.12f, 0.12f, 0.15f, 1.0f);
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_LINE_SMOOTH);
    glEnable(GL_POINT_SMOOTH);
    glHint(GL_LINE_SMOOTH_HINT, GL_NICEST);

    // Phong shader
    m_phongProg = new QOpenGLShaderProgram;
    m_phongProg->addShaderFromSourceFile(QOpenGLShader::Vertex, "shaders/phong.vert");
    m_phongProg->addShaderFromSourceFile(QOpenGLShader::Fragment, "shaders/phong.frag");
    m_phongProg->link();

    // Line shader
    m_lineProg = new QOpenGLShaderProgram;
    m_lineProg->addShaderFromSourceFile(QOpenGLShader::Vertex, "shaders/line.vert");
    m_lineProg->addShaderFromSourceFile(QOpenGLShader::Fragment, "shaders/line.frag");
    m_lineProg->link();

    m_glReady = true;
    if (m_dirty) uploadBatches();
}

void GLWidget::resizeGL(int w, int h) {
    m_cam.setViewport(w, h);
}

GLBatch GLWidget::doUploadLine(const DrawBatch& b) {
    GLBatch gl;
    gl.vertCount = (int)(b.vertices.size() / 3);
    gl.hasNormals = false;
    gl.hasIndices = false;
    glGenVertexArrays(1, &gl.vao);
    glBindVertexArray(gl.vao);

    glGenBuffers(1, &gl.vbo);
    glBindBuffer(GL_ARRAY_BUFFER, gl.vbo);
    glBufferData(GL_ARRAY_BUFFER, b.vertices.size()*sizeof(float), b.vertices.data(), GL_STATIC_DRAW);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
    glEnableVertexAttribArray(0);

    glGenBuffers(1, &gl.cbo);
    glBindBuffer(GL_ARRAY_BUFFER, gl.cbo);
    glBufferData(GL_ARRAY_BUFFER, b.colors.size()*sizeof(float), b.colors.data(), GL_STATIC_DRAW);
    glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 0, nullptr);
    glEnableVertexAttribArray(1);

    glBindVertexArray(0);
    return gl;
}

GLBatch GLWidget::doUploadTri(const DrawBatch& b) {
    GLBatch gl;
    gl.indexCount = (int)b.indices.size();
    gl.vertCount = (int)(b.vertices.size() / 3);
    gl.hasNormals = !b.normals.empty();
    gl.hasIndices = !b.indices.empty();

    glGenVertexArrays(1, &gl.vao);
    glBindVertexArray(gl.vao);

    glGenBuffers(1, &gl.vbo);
    glBindBuffer(GL_ARRAY_BUFFER, gl.vbo);
    glBufferData(GL_ARRAY_BUFFER, b.vertices.size()*sizeof(float), b.vertices.data(), GL_STATIC_DRAW);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
    glEnableVertexAttribArray(0);

    if (gl.hasNormals) {
        glGenBuffers(1, &gl.nbo);
        glBindBuffer(GL_ARRAY_BUFFER, gl.nbo);
        glBufferData(GL_ARRAY_BUFFER, b.normals.size()*sizeof(float), b.normals.data(), GL_STATIC_DRAW);
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
        glEnableVertexAttribArray(1);
    }

    glGenBuffers(1, &gl.cbo);
    glBindBuffer(GL_ARRAY_BUFFER, gl.cbo);
    int colorLoc = gl.hasNormals ? 2 : 1;
    glBufferData(GL_ARRAY_BUFFER, b.colors.size()*sizeof(float), b.colors.data(), GL_STATIC_DRAW);
    glVertexAttribPointer(colorLoc, 4, GL_FLOAT, GL_FALSE, 0, nullptr);
    glEnableVertexAttribArray(colorLoc);

    if (gl.hasIndices) {
        glGenBuffers(1, &gl.ebo);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, gl.ebo);
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, b.indices.size()*sizeof(unsigned int), b.indices.data(), GL_STATIC_DRAW);
    }
    glBindVertexArray(0);
    return gl;
}

void GLWidget::uploadBatches() {
    m_glBatches.clear();
    m_glTracks.clear();
    m_glHits.clear();

    for (auto& b : m_scene.batches) {
        if (b.wireframe || b.normals.empty())
            m_glBatches.push_back(doUploadLine(b));
        else
            m_glBatches.push_back(doUploadTri(b));
    }
    for (auto& t : m_scene.trackLines) m_glTracks.push_back(doUploadLine(t));
    for (auto& h : m_scene.hitPoints)   m_glHits.push_back(doUploadLine(h));
    m_glBeam = doUploadLine(m_scene.beamArrow);
    m_dirty = false;
}

void GLWidget::paintGL() {
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    auto view = m_cam.viewMatrix();
    auto proj = m_cam.projectionMatrix();

    // --- Phong pass（实体几何） ---
    m_phongProg->bind();
    QMatrix4x4 model;
    m_phongProg->setUniformValue("uMVP", proj * view * model);
    m_phongProg->setUniformValue("uModel", model);
    m_phongProg->setUniformValue("uLightDir", QVector3D(0.5f, 0.8f, 1.0f));
    m_phongProg->setUniformValue("uAlpha", 0.6f);

    glDepthMask(GL_FALSE);
    int idx = 0;
    for (auto& gl : m_glBatches) {
        if (idx < (int)m_scene.batches.size() && !m_scene.batches[idx].wireframe && !m_scene.batches[idx].normals.empty()) {
            m_phongProg->setUniformValue("uAlpha", m_scene.batches[idx].alpha);
            glBindVertexArray(gl.vao);
            if (gl.hasIndices)
                glDrawElements(GL_TRIANGLES, gl.indexCount, GL_UNSIGNED_INT, nullptr);
            else
                glDrawArrays(GL_TRIANGLES, 0, gl.vertCount);
        }
        idx++;
    }
    glDepthMask(GL_TRUE);
    m_phongProg->release();

    // --- Line pass（线框、轨迹、碰撞点） ---
    m_lineProg->bind();
    m_lineProg->setUniformValue("uMVP", proj * view * model);

    // 线框层 + 世界框
    idx = 0;
    for (auto& gl : m_glBatches) {
        if (idx < (int)m_scene.batches.size() && m_scene.batches[idx].wireframe) {
            glLineWidth(m_scene.batches[idx].lineWidth);
            glBindVertexArray(gl.vao);
            glDrawArrays(GL_LINES, 0, gl.vertCount);
        }
        idx++;
    }

    // 轨迹
    for (size_t i = 0; i < m_glTracks.size() && i < m_scene.trackLines.size(); i++) {
        glLineWidth(m_scene.trackLines[i].lineWidth);
        glBindVertexArray(m_glTracks[i].vao);
        glDrawArrays(GL_LINE_STRIP, 0, m_glTracks[i].vertCount);
    }

    // 碰撞点
    for (size_t i = 0; i < m_glHits.size() && i < m_scene.hitPoints.size(); i++) {
        glLineWidth(m_scene.hitPoints[i].lineWidth);
        glPointSize(m_scene.hitPoints[i].lineWidth);
        glBindVertexArray(m_glHits[i].vao);
        glDrawArrays(GL_POINTS, 0, m_glHits[i].vertCount);
    }

    // 入射箭头
    glLineWidth(m_scene.beamArrow.lineWidth);
    glBindVertexArray(m_glBeam.vao);
    glDrawArrays(GL_LINES, 0, m_glBeam.vertCount);

    m_lineProg->release();
    glBindVertexArray(0);
}

void GLWidget::mousePressEvent(QMouseEvent* e) {
    m_lastMouse = e->pos();
    m_leftDown   = (e->button() == Qt::LeftButton);
    m_rightDown  = (e->button() == Qt::RightButton);
    m_middleDown = (e->button() == Qt::MiddleButton);
}

void GLWidget::mouseReleaseEvent(QMouseEvent*) {
    m_leftDown = m_rightDown = m_middleDown = false;
}

void GLWidget::mouseMoveEvent(QMouseEvent* e) {
    QPointF delta = e->pos() - m_lastMouse;
    m_lastMouse = e->pos();

    if (m_leftDown) {
        m_cam.rotate(delta);
    } else if (m_rightDown || m_middleDown) {
        m_cam.pan(delta);
    }
    update();
}

void GLWidget::wheelEvent(QWheelEvent* e) {
    float d = e->angleDelta().y() / 120.0f;
    m_cam.zoom(d);
    update();
}
