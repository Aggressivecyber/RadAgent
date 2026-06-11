// DetectorConstruction.cc
// Implementation of detector geometry from G4ModelIR
// Components: world (G4_AIR), silicon_detector (G4_Si), oxide_layer (G4_SILICON_DIOXIDE),
//             aluminum_shield (G4_Al)

#include "DetectorConstruction.hh"
#include "MaterialRegistry.hh"
#include "PlacementManager.hh"
#include "SensitiveDetector.hh"
#include "ScoringManager.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4SDManager.hh"
#include "G4VisAttributes.hh"
#include "G4Colour.hh"
#include "globals.hh"

DetectorConstruction::DetectorConstruction()
    : G4VUserDetectorConstruction(),
      fMaterialRegistry(nullptr),
      fPlacementManager(nullptr)
{
}

DetectorConstruction::~DetectorConstruction() = default;

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    // Initialize registries
    fMaterialRegistry = &MaterialRegistry::Instance();
    fPlacementManager = &PlacementManager::Instance();

    // Define all materials from G4ModelIR
    DefineMaterials();

    // Build geometry hierarchy
    BuildGeometry();

    return fPlacementManager->GetWorldVolume();
}

void DetectorConstruction::DefineMaterials()
{
    // All materials are NIST; initialize registry with material_ids from G4ModelIR
    fMaterialRegistry->Initialize({
        {"G4_AIR", "G4_AIR"},
        {"G4_Si", "G4_Si"},
        {"G4_SILICON_DIOXIDE", "G4_SILICON_DIOXIDE"},
        {"G4_Al", "G4_Al"}
    });
}

    constexpr G4double kShieldVisGrey = 0.6;

void DetectorConstruction::BuildGeometry()
{
    // World volume: Box 200x200x200 mm (full length), G4_AIR
    // Half-lengths for G4Box constructor
    const G4double world_hx = 100.0 * mm;
    const G4double world_hy = 100.0 * mm;
    const G4double world_hz = 100.0 * mm;

    G4Material* world_mat = fMaterialRegistry->GetMaterial("G4_AIR");
    G4Box* world_solid = new G4Box("World", world_hx, world_hy, world_hz);
    G4LogicalVolume* world_lv = new G4LogicalVolume(world_solid, world_mat, "World");

    G4VPhysicalVolume* world_pv = new G4PVPlacement(
        nullptr,                    // no rotation
        G4ThreeVector(0, 0, 0),     // at origin
        world_lv,                   // logical volume
        "World",                    // name
        nullptr,                    // mother volume (null = world)
        false,                      // no boolean operations
        0,                          // copy number
        true                        // check overlaps
    );

    // Initialize PlacementManager with world PV
    fPlacementManager->Initialize(world_pv);

    // --- Component: silicon_detector ---
    // Box 20x20x0.5 mm, G4_Si, position (0,0,0) in world
    // Half-lengths for G4Box constructor
    G4Material* si_mat = fMaterialRegistry->GetMaterial("G4_Si");
    G4Box* si_solid = new G4Box("SiliconDetector", 10.0 * mm, 10.0 * mm, 0.25 * mm);
    G4LogicalVolume* si_lv = new G4LogicalVolume(si_solid, si_mat, "SiliconDetector");

    fPlacementManager->PlaceVolume(
        "silicon_detector",
        si_lv,
        "world",
        G4ThreeVector(0.0, 0.0, 0.0),  // position from G4ModelIR
        nullptr,                         // no rotation
        true                             // check overlaps
    );

    // Store as scoring volume
    fScoringVolumes["silicon_detector"] = si_lv;

    // --- Component: oxide_layer ---
    // Box 20x20x0.02 mm, G4_SILICON_DIOXIDE, position (0,0,0.27 cm) in world
    // Half-lengths for G4Box constructor
    G4Material* oxide_mat = fMaterialRegistry->GetMaterial("G4_SILICON_DIOXIDE");
    G4Box* oxide_solid = new G4Box("OxideLayer", 10.0 * mm, 10.0 * mm, 0.01 * mm);
    G4LogicalVolume* oxide_lv = new G4LogicalVolume(oxide_solid, oxide_mat, "OxideLayer");

    fPlacementManager->PlaceVolume(
        "oxide_layer",
        oxide_lv,
        "world",
        G4ThreeVector(0.0, 0.0, 0.27 * mm),  // position from G4ModelIR
        nullptr,                               // no rotation
        true                                   // check overlaps
    );

    // --- Component: aluminum_shield ---
    // Box 30x30x1.0 mm, G4_Al, position (0,0,-10 cm) in world
    // Half-lengths for G4Box constructor
    G4Material* al_mat = fMaterialRegistry->GetMaterial("G4_Al");
    G4Box* al_solid = new G4Box("AluminumShield", 15.0 * mm, 15.0 * mm, 0.5 * mm);
    G4LogicalVolume* al_lv = new G4LogicalVolume(al_solid, al_mat, "AluminumShield");

    fPlacementManager->PlaceVolume(
        "aluminum_shield",
        al_lv,
        "world",
        G4ThreeVector(0.0, 0.0, -10.0 * mm),  // position from G4ModelIR
        nullptr,                                // no rotation
        true                                    // check overlaps
    );

    // Visualization attributes
    G4VisAttributes world_vis(G4Colour::White());
    world_vis.SetVisibility(false);
    world_lv->SetVisAttributes(world_vis);

    G4VisAttributes si_vis(G4Colour::Yellow());
    si_lv->SetVisAttributes(si_vis);

    G4VisAttributes oxide_vis(G4Colour::Cyan());
    oxide_lv->SetVisAttributes(oxide_vis);

    G4VisAttributes al_vis(G4Colour(kShieldVisGrey, kShieldVisGrey, kShieldVisGrey));  // grey
    al_lv->SetVisAttributes(al_vis);

    G4cout << "==== Detector Geometry Built ====" << G4endl
           << "  World: 200x200x200 mm (G4_AIR)" << G4endl
           << "  SiliconDetector: 20x20x0.5 mm (G4_Si) at (0,0,0)" << G4endl
           << "  OxideLayer: 20x20x0.02 mm (G4_SILICON_DIOXIDE) at (0,0,0.27mm)" << G4endl
           << "  AluminumShield: 30x30x1.0 mm (G4_Al) at (0,0,-10mm)" << G4endl;
}

void DetectorConstruction::ConstructSDandField()
{
    AttachSensitiveDetectors();
}

void DetectorConstruction::AttachSensitiveDetectors()
{
    // Register SensitiveDetector for silicon_detector volume
    // SD is defined in SensitiveDetector class; collection name "SiliconHits"
    // for edep_MeV scoring on the silicon substrate
    G4LogicalVolume* si_lv = fPlacementManager->GetLogicalVolume("silicon_detector");
    if (!si_lv) {
        G4ExceptionDescription msg;
        msg << "Silicon detector logical volume not found in PlacementManager."
            << " Cannot attach sensitive detector.";
        G4Exception("DetectorConstruction::AttachSensitiveDetectors",
                    "DetConst001", FatalException, msg);
        return;
    }

    // SensitiveDetector class will be defined in SensitiveDetector module
    // Its ProcessHits records edep_MeV; ScoringManager aggregates dose_Gy
    auto* sd = new SensitiveDetector("SensitiveDetector", "SiliconHits");
    G4SDManager::GetSDMpointer()->AddNewDetector(sd);
    
    ScoringManager::Instance().Initialize(si_lv);
SetSensitiveDetector(si_lv, sd);

    G4cout << "SensitiveDetector attached to SiliconDetector logical volume"
           << G4endl;
}

G4LogicalVolume* DetectorConstruction::GetScoringVolume(const G4String& name) const
{
    auto it = fScoringVolumes.find(name);
    if (it != fScoringVolumes.end()) {
        return it->second;
    }
    return nullptr;
}

MaterialRegistry* DetectorConstruction::GetMaterialRegistry() const
{
    return fMaterialRegistry;
}

PlacementManager* DetectorConstruction::GetPlacementManager() const
{
    return fPlacementManager;
}