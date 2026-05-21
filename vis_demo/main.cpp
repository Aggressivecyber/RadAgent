#include "GLWidget.h"
#include "SceneBuilder.h"
#include "ParticleData.h"

#include <QApplication>
#include <QMainWindow>
#include <QDockWidget>
#include <QTextEdit>
#include <QToolBar>
#include <QAction>
#include <QVBoxLayout>
#include <QLabel>
#include <QGroupBox>

// 构建演示数据：典型航天多层屏蔽 + 质子入射
static SimData buildDemoData() {
    SimData sim;
    sim.worldSize = 40.0f;
    sim.beamEnergy = 100;  // MeV 质子
    sim.beamX = 0; sim.beamY = 0;

    // 多层屏蔽（从上到下排列）
    sim.layers = {
        {"Aluminum",     0.3f,  2.70f, {0.75f, 0.78f, 0.82f}},  // 铝外壳
        {"Polyethylene", 2.0f,  0.95f, {0.2f,  0.6f,  0.9f}},  // PE 含氢材料
        {"Tantalum",     0.5f, 16.69f, {0.55f, 0.45f, 0.55f}},  // 钽高Z
        {"Polyethylene", 3.0f,  0.95f, {0.2f,  0.7f,  0.85f}}, // PE 二次含氢
        {"Aluminum",     0.3f,  2.70f, {0.75f, 0.78f, 0.82f}},  // 铝背壳
    };

    // 模拟一些粒子轨迹
    auto addTrack = [&](int eid, int tid, int pid, const QString& name,
                        float energy, std::vector<TrackPoint> pts) {
        Track t;
        t.eventId = eid; t.trackId = tid; t.parentId = pid;
        t.particle = name; t.initialEnergy = energy;
        t.color = particleColor(name);
        t.points = std::move(pts);
        sim.tracks.push_back(std::move(t));
    };

    // Event 0: 100 MeV 质子直接穿透
    addTrack(0, 1, 0, "proton", 100, {
        {{0, 0, 20}, 0, 100},
        {{0.1, -0.05, 14.5}, 0.8, 99.2},
        {{0.15, -0.1, 11.5}, 0.5, 98.7},
        {{0.2, -0.08, 8.5}, 1.2, 97.5},
        {{0.3, -0.15, 5.5}, 2.5, 95.0},
        {{0.5, -0.2, 2.5}, 5.0, 90.0},
        {{0.8, -0.3, -2}, 8.0, 82.0},
        {{1.2, -0.5, -6}, 3.0, 79.0},
        {{1.5, -0.8, -10}, 1.5, 77.5},
        {{2.0, -1.2, -15}, 0.5, 77.0},
        {{2.5, -1.5, -20}, 0.1, 76.9},
    });

    // Event 0: 质子产生的次级中子
    addTrack(0, 2, 1, "neutron", 15, {
        {{0.3, -0.15, 5.5}, 0, 15},
        {{0.8, 0.5, 3.0}, 0.5, 14.5},
        {{1.5, 1.2, 0.5}, 1.0, 13.5},
        {{2.5, 2.0, -2}, 2.0, 11.5},
        {{3.5, 2.8, -5}, 1.5, 10.0},
        {{4.0, 3.0, -8}, 0.5, 9.5},
    });

    // Event 0: 次级伽马
    addTrack(0, 3, 1, "gamma", 5, {
        {{0.15, -0.1, 11.5}, 0, 5},
        {{0.15, -0.5, 8.0}, 0.3, 4.7},
        {{0.15, -1.0, 4.0}, 0.5, 4.2},
        {{0.15, -1.5, 0.0}, 1.0, 3.2},
        {{0.15, -2.0, -4}, 0.8, 2.4},
        {{0.15, -2.5, -8}, 0.2, 2.2},
    });

    // Event 1: 100 MeV 质子偏转
    addTrack(1, 1, 0, "proton", 100, {
        {{0.5, 0.3, 20}, 0, 100},
        {{0.6, 0.2, 14.5}, 0.9, 99.1},
        {{0.8, 0.0, 11.5}, 0.6, 98.5},
        {{1.2, -0.3, 8.5}, 1.5, 97.0},
        {{2.0, -0.8, 5.5}, 3.0, 94.0},
        {{3.0, -1.5, 2.5}, 6.0, 88.0},
        {{4.5, -2.5, -2}, 10.0, 78.0},
        {{6.0, -3.5, -6}, 5.0, 73.0},
        {{7.5, -4.0, -10}, 2.0, 71.0},
        {{8.0, -4.2, -15}, 0.3, 70.7},
    });

    // Event 1: 次级电子
    addTrack(1, 2, 1, "e-", 2, {
        {{2.0, -0.8, 5.5}, 0, 2},
        {{2.3, -1.0, 4.5}, 0.2, 1.8},
        {{2.8, -1.5, 3.5}, 0.3, 1.5},
        {{3.5, -2.0, 2.5}, 0.5, 1.0},
        {{4.0, -2.3, 1.5}, 0.4, 0.6},
        {{4.2, -2.5, 0.5}, 0.3, 0.3},
    });

    // Event 2: 高能质子深穿透
    addTrack(2, 1, 0, "proton", 200, {
        {{-0.3, 0.2, 20}, 0, 200},
        {{-0.2, 0.15, 14.5}, 0.3, 199.7},
        {{-0.15, 0.1, 11.5}, 0.2, 199.5},
        {{-0.1, 0.05, 8.5}, 0.4, 199.1},
        {{0.0, -0.05, 5.5}, 0.8, 198.3},
        {{0.2, -0.1, 2.5}, 1.5, 196.8},
        {{0.3, -0.15, -2}, 2.0, 194.8},
        {{0.5, -0.2, -6}, 1.0, 193.8},
        {{0.8, -0.3, -10}, 0.5, 193.3},
        {{1.0, -0.4, -15}, 0.2, 193.1},
        {{1.2, -0.5, -20}, 0.1, 193.0},
    });

    // 碰撞点（能量沉积）
    for (auto& trk : sim.tracks) {
        for (auto& pt : trk.points) {
            if (pt.edep > 0.3f) {
                HitPoint h;
                h.pos = pt.pos;
                h.edep = pt.edep;
                h.particle = trk.particle;
                h.eventId = trk.eventId;
                sim.hits.push_back(h);
            }
        }
    }

    return sim;
}

static QString buildInfoText(const SimData& sim) {
    QString info;
    info += "<h3>RadAgent 3D Visualization Demo</h3>";
    info += "<hr>";

    info += "<h4>Beam Configuration</h4>";
    info += QString("<table>"
        "<tr><td><b>Particle:</b></td><td>proton</td></tr>"
        "<tr><td><b>Energy:</b></td><td>%1 MeV</td></tr>"
        "<tr><td><b>Position:</b></td><td>(%2, %3)</td></tr>"
        "<tr><td><b>Direction:</b></td><td>(0, 0, -1)</td></tr>"
        "</table><br>")
        .arg(sim.beamEnergy).arg(sim.beamX).arg(sim.beamY);

    info += "<h4>Shield Layers (top → bottom)</h4>";
    info += "<table cellpadding='3'>";
    info += "<tr><th>Material</th><th>Thickness</th><th>Density</th></tr>";
    for (auto& l : sim.layers) {
        info += QString("<tr><td>%1</td><td>%2 cm</td><td>%3 g/cm³</td></tr>")
            .arg(l.material).arg(l.thickness, 0, 'f', 1).arg(l.density, 0, 'f', 2);
    }
    info += "</table><br>";

    info += "<h4>Particle Tracks</h4>";
    info += QString("<p>Total tracks: %1</p>").arg(sim.tracks.size());
    info += "<table cellpadding='2'>";
    info += "<tr><th>Event</th><th>Particle</th><th>Energy</th><th>Steps</th></tr>";
    for (auto& t : sim.tracks) {
        info += QString("<tr><td>%1</td><td><font color='%2'>%3</font></td>"
                        "<td>%4 MeV</td><td>%5</td></tr>")
            .arg(t.eventId)
            .arg(t.color.name())
            .arg(t.particle)
            .arg(t.initialEnergy, 0, 'f', 1)
            .arg(t.points.size());
    }
    info += "</table><br>";

    info += "<h4>Energy Deposition Hits</h4>";
    info += QString("<p>Total hits: %1</p>").arg(sim.hits.size());

    info += "<hr>";
    info += "<h4>Controls</h4>";
    info += "<ul>";
    info += "<li><b>Left mouse</b>: Rotate</li>";
    info += "<li><b>Right/Middle mouse</b>: Pan</li>";
    info += "<li><b>Scroll wheel</b>: Zoom</li>";
    info += "<li><b>R key</b>: Reset camera</li>";
    info += "</ul>";

    return info;
}

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    app.setApplicationName("RadAgent Visualization");

    auto sim = buildDemoData();
    auto scene = buildScene(sim);

    QMainWindow win;
    win.setWindowTitle("RadAgent 3D Visualization — Multilayer Shield + Particle Trajectories");
    win.resize(1200, 800);

    // GL viewport
    auto glWidget = new GLWidget(&win);
    glWidget->setScene(std::move(scene));
    win.setCentralWidget(glWidget);

    // Info dock
    auto dock = new QDockWidget("Simulation Info", &win);
    dock->setFeatures(QDockWidget::DockWidgetMovable | QDockWidget::DockWidgetFloatable);
    auto infoText = new QTextEdit(dock);
    infoText->setReadOnly(true);
    infoText->setHtml(buildInfoText(sim));
    dock->setWidget(infoText);
    dock->setMinimumWidth(280);
    win.addDockWidget(Qt::RightDockWidgetArea, dock);

    // Toolbar
    auto toolbar = win.addToolBar("View");
    auto resetAction = toolbar->addAction("Reset Camera");
    QObject::connect(resetAction, &QAction::triggered, glWidget, &GLWidget::resetCamera);

    win.show();
    return app.exec();
}
