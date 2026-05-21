#include "ParticleData.h"
#include <QStringList>

QColor particleColor(const QString& name) {
    static const std::map<QString, QColor> colors = {
        {"proton",      {255, 80, 80}},
        {"gamma",       {255, 255, 50}},
        {"e-",          {80, 150, 255}},
        {"e+",          {80, 255, 150}},
        {"neutron",     {180, 180, 180}},
        {"alpha",       {255, 160, 50}},
        {"mu-",         {200, 80, 255}},
        {"mu+",         {255, 80, 200}},
        {"pi+",         {255, 200, 100}},
        {"pi-",         {100, 200, 255}},
        {"deuteron",    {255, 100, 150}},
        {"triton",      {150, 100, 255}},
        {"He3",         {100, 255, 200}},
    };
    auto it = colors.find(name);
    if (it != colors.end()) return it->second;
    return {200, 200, 200};
}
