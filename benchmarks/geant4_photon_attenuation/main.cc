#include "G4Box.hh"
#include "G4DecayPhysics.hh"
#include "G4Element.hh"
#include "G4EmStandardPhysics.hh"
#include "G4Gamma.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4ParticleGun.hh"
#include "G4PhysicalConstants.hh"
#include "G4RunManager.hh"
#include "G4Step.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4Track.hh"
#include "G4UserEventAction.hh"
#include "G4UserSteppingAction.hh"
#include "G4VModularPhysicsList.hh"
#include "G4VUserActionInitialization.hh"
#include "G4VUserDetectorConstruction.hh"
#include "G4VUserPrimaryGeneratorAction.hh"
#include "Randomize.hh"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>

namespace {

struct Config {
  std::string material = "Pb";
  double density_g_cm3 = 11.34;
  double energy_MeV = 1.0;
  double thickness_cm = 1.0;
  int events = 10000;
  long seed = 12345;
};

struct Score {
  int transmitted = 0;
  bool primary_interacted = false;
};

std::string value_for(int argc, char** argv, const std::string& name, std::string fallback) {
  for (int i = 1; i + 1 < argc; ++i) {
    if (argv[i] == name) {
      return argv[i + 1];
    }
  }
  return fallback;
}

Config parse_config(int argc, char** argv) {
  Config config;
  config.material = value_for(argc, argv, "--material", config.material);
  config.density_g_cm3 = std::stod(value_for(argc, argv, "--density", std::to_string(config.density_g_cm3)));
  config.energy_MeV = std::stod(value_for(argc, argv, "--energy", std::to_string(config.energy_MeV)));
  config.thickness_cm = std::stod(value_for(argc, argv, "--thickness", std::to_string(config.thickness_cm)));
  config.events = std::stoi(value_for(argc, argv, "--events", std::to_string(config.events)));
  config.seed = std::stol(value_for(argc, argv, "--seed", std::to_string(config.seed)));
  if (config.thickness_cm <= 0.0 || config.events <= 0 || config.energy_MeV <= 0.0) {
    throw std::runtime_error("energy, thickness, and events must be positive");
  }
  return config;
}

G4Material* build_material(const Config& config) {
  auto* nist = G4NistManager::Instance();
  const auto density = config.density_g_cm3 * g / cm3;
  if (config.material == "Pb") {
    auto* material = new G4Material("BenchmarkPb", density, 1);
    material->AddElement(nist->FindOrBuildElement("Pb"), 1);
    return material;
  }
  if (config.material == "Al") {
    auto* material = new G4Material("BenchmarkAl", density, 1);
    material->AddElement(nist->FindOrBuildElement("Al"), 1);
    return material;
  }
  if (config.material == "Water") {
    auto* material = new G4Material("BenchmarkWater", density, 2);
    material->AddElement(nist->FindOrBuildElement("H"), 2);
    material->AddElement(nist->FindOrBuildElement("O"), 1);
    return material;
  }
  throw std::runtime_error("unsupported material: " + config.material);
}

class DetectorConstruction final : public G4VUserDetectorConstruction {
 public:
  explicit DetectorConstruction(Config config) : config_(std::move(config)) {}

  G4VPhysicalVolume* Construct() override {
    auto* nist = G4NistManager::Instance();
    auto* vacuum = nist->FindOrBuildMaterial("G4_Galactic");
    auto* slab_material = build_material(config_);

    const auto slab_z = config_.thickness_cm * cm;
    const auto world_xy = 20.0 * cm;
    const auto world_z = slab_z + 20.0 * cm;
    auto* world_solid = new G4Box("World", world_xy / 2.0, world_xy / 2.0, world_z / 2.0);
    auto* world_logic = new G4LogicalVolume(world_solid, vacuum, "World");
    auto* world_phys = new G4PVPlacement(
        nullptr, G4ThreeVector(), world_logic, "World", nullptr, false, 0, true);

    auto* slab_solid = new G4Box("Slab", 5.0 * cm, 5.0 * cm, slab_z / 2.0);
    auto* slab_logic = new G4LogicalVolume(slab_solid, slab_material, "Slab");
    new G4PVPlacement(nullptr, G4ThreeVector(), slab_logic, "Slab", world_logic, false, 0, true);

    auto* downstream_solid = new G4Box("Downstream", 5.0 * cm, 5.0 * cm, 0.5 * mm);
    auto* downstream_logic = new G4LogicalVolume(downstream_solid, vacuum, "Downstream");
    new G4PVPlacement(
        nullptr,
        G4ThreeVector(0.0, 0.0, slab_z / 2.0 + 0.5 * mm),
        downstream_logic,
        "Downstream",
        world_logic,
        false,
        0,
        true);
    return world_phys;
  }

 private:
  Config config_;
};

class PrimaryGenerator final : public G4VUserPrimaryGeneratorAction {
 public:
  explicit PrimaryGenerator(Config config) : config_(std::move(config)) {
    gun_ = new G4ParticleGun(1);
    gun_->SetParticleDefinition(G4Gamma::GammaDefinition());
    gun_->SetParticleEnergy(config_.energy_MeV * MeV);
    gun_->SetParticleMomentumDirection(G4ThreeVector(0.0, 0.0, 1.0));
  }

  ~PrimaryGenerator() override { delete gun_; }

  void GeneratePrimaries(G4Event* event) override {
    const auto slab_z = config_.thickness_cm * cm;
    gun_->SetParticlePosition(G4ThreeVector(0.0, 0.0, -slab_z / 2.0 - 1.0 * cm));
    gun_->GeneratePrimaryVertex(event);
  }

 private:
  Config config_;
  G4ParticleGun* gun_ = nullptr;
};

class PhysicsList final : public G4VModularPhysicsList {
 public:
  PhysicsList() {
    SetVerboseLevel(0);
    RegisterPhysics(new G4EmStandardPhysics());
    RegisterPhysics(new G4DecayPhysics());
  }
};

class SteppingAction final : public G4UserSteppingAction {
 public:
  explicit SteppingAction(Score& score) : score_(score) {}

  void UserSteppingAction(const G4Step* step) override {
    const auto* track = step->GetTrack();
    if (track->GetTrackID() != 1 || track->GetParentID() != 0) {
      return;
    }
    const auto* pre = step->GetPreStepPoint()->GetPhysicalVolume();
    const auto* post = step->GetPostStepPoint()->GetPhysicalVolume();
    if (pre == nullptr || post == nullptr) {
      return;
    }
    const auto* process = step->GetPostStepPoint()->GetProcessDefinedStep();
    if (pre->GetName() == "Slab" && process != nullptr && process->GetProcessName() != "Transportation") {
      score_.primary_interacted = true;
    }
    if (pre->GetName() == "Slab" && post->GetName() == "Downstream") {
      if (!score_.primary_interacted) {
        ++score_.transmitted;
      }
      const_cast<G4Track*>(track)->SetTrackStatus(fStopAndKill);
    }
  }

 private:
  Score& score_;
};

class EventAction final : public G4UserEventAction {
 public:
  explicit EventAction(Score& score) : score_(score) {}

  void BeginOfEventAction(const G4Event*) override { score_.primary_interacted = false; }

 private:
  Score& score_;
};

class ActionInitialization final : public G4VUserActionInitialization {
 public:
  ActionInitialization(Config config, Score& score)
      : config_(std::move(config)), score_(score) {}

  void Build() const override {
    SetUserAction(new PrimaryGenerator(config_));
    SetUserAction(new EventAction(score_));
    SetUserAction(new SteppingAction(score_));
  }

 private:
  Config config_;
  Score& score_;
};

}  // namespace

int main(int argc, char** argv) {
  try {
    auto config = parse_config(argc, argv);
    CLHEP::HepRandom::setTheSeed(config.seed);
    Score score;

    auto* run_manager = new G4RunManager();
    run_manager->SetUserInitialization(new DetectorConstruction(config));
    run_manager->SetUserInitialization(new PhysicsList());
    run_manager->SetUserInitialization(new ActionInitialization(config, score));
    run_manager->Initialize();
    run_manager->BeamOn(config.events);
    delete run_manager;

    const auto transmission = static_cast<double>(score.transmitted) / config.events;
    std::cout << "{"
              << "\"material\":\"" << config.material << "\","
              << "\"density_g_cm3\":" << config.density_g_cm3 << ","
              << "\"energy_MeV\":" << config.energy_MeV << ","
              << "\"thickness_cm\":" << config.thickness_cm << ","
              << "\"events\":" << config.events << ","
              << "\"transmitted\":" << score.transmitted << ","
              << "\"transmission\":" << transmission << ","
              << "\"seed\":" << config.seed
              << "}" << std::endl;
    return EXIT_SUCCESS;
  } catch (const std::exception& exc) {
    std::cerr << "photon_attenuation benchmark failed: " << exc.what() << std::endl;
    return EXIT_FAILURE;
  }
}
