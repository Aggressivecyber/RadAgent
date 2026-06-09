"""Document store — Geant4 knowledge base for RAG retrieval.

Provides pre-built document collections for embedding and indexing.
Documents cover core Geant4 concepts: geometry, materials, physics,
scoring, sensitive detectors, and run management.

Usage:
    store = Geant4DocStore()
    docs = store.get_documents()  # list[RAGDocument]
    # Feed to RAGClient.index_documents(docs)
"""

from __future__ import annotations

from .rag_client import RAGDocument

# ---------------------------------------------------------------------------
# Geant4 core knowledge base — curated from official Geant4 documentation
# ---------------------------------------------------------------------------

_G4_DOCUMENTS: list[dict[str, str]] = [
    {
        "doc_id": "g4_geometry_box",
        "title": "G4Box — Box Solid",
        "content": (
            "G4Box(const G4String& pName, G4double pDx, G4double pDy, G4double pDz) "
            "creates a box solid with half-lengths dx, dy, dz. The full dimensions are "
            "2*dx × 2*dy × 2*dz. G4Box is the simplest solid and is commonly used for "
            'world volumes and layer geometries. Include: #include "G4Box.hh". '
            "Units: use G4SystemOfUnits.hh (mm, cm, m)."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_geometry_tubs",
        "title": "G4Tubs — Cylindrical Solid",
        "content": (
            "G4Tubs(const G4String& pName, G4double pRMin, G4double pRMax, "
            "G4double pDz, G4double pSPhi, G4double pDPhi) creates a tube or cylinder. "
            "pRMin/pRMax: inner/outer radius. pDz: half-length in z. "
            "pSPhi/pDPhi: starting angle and delta angle. For a full cylinder set "
            "pRMin=0, pDPhi=360*deg. Commonly used for detector layers, beam pipes. "
            'Include: #include "G4Tubs.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_geometry_sphere",
        "title": "G4Sphere — Spherical Shell Solid",
        "content": (
            "G4Sphere(const G4String& pName, G4double pRMin, G4double pRMax, "
            "G4double pSPhi, G4double pDPhi, G4double pSTheta, G4double pDTheta) "
            "creates a spherical shell. pRMin/pRMax: inner/outer radius. "
            "For a solid sphere set pRMin=0. Used for spherical detectors, shielding. "
            'Include: #include "G4Sphere.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_geometry_trap",
        "title": "G4Trap — Trapezoid Solid",
        "content": (
            "G4Trap(const G4String& pName, G4double pDz, G4double pTheta, G4double pPhi, "
            "G4double pDy1, G4double pDx1, G4double pDx2, G4double pAlp1, "
            "G4double pDy2, G4double pDx3, G4double pDx4, G4double pAlp2) "
            "creates a general trapezoid. Used for non-rectangular detector shapes. "
            "A simpler constructor exists for symmetric traps: G4Box-like with taper. "
            'Include: #include "G4Trap.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_geometry_polycone",
        "title": "G4Polycone — Polycone Solid",
        "content": (
            "G4Polycone(const G4String& pName, G4double pSPhi, G4double pDPhi, "
            "G4int numZPlanes, const G4double* pZ, const G4double* pRMin, "
            "const G4double* pRMax) creates a solid of revolution defined by z-planes "
            "with inner/outer radii. Used for complex cylindrical detector geometries. "
            'Include: #include "G4Polycone.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_logical_volume",
        "title": "G4LogicalVolume — Logical Volume",
        "content": (
            "G4LogicalVolume(G4VSolid* pSolid, G4Material* pMaterial, "
            "const G4String& pName) binds a solid shape with a material. "
            "Logical volumes define the properties but NOT the position. "
            "A logical volume can be placed multiple times. "
            "Sensitive detectors are attached to logical volumes via "
            'SetSensitiveDetector(). Include: #include "G4LogicalVolume.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_physical_volume",
        "title": "G4PVPlacement — Physical Volume Placement",
        "content": (
            "G4PVPlacement(G4RotationMatrix* pRot, const G4ThreeVector& pTrans, "
            "G4LogicalVolume* pLogical, const G4String& pName, "
            "G4LogicalVolume* pMotherLogical, G4bool pMany, G4int pCopyNo, "
            "G4bool pOverlaps=false) places a logical volume inside a mother "
            "logical volume. Prefer this logical-mother constructor for generated "
            "RadAgent placement code: new G4PVPlacement(rotation, position, "
            "logical, name, motherLogical, many, copyNo, checkOverlaps). "
            "Position and rotation are in the mother's coordinate system. "
            "The world volume has no mother (nullptr). Set pOverlaps=true to enable "
            'overlap checking. Include: #include "G4PVPlacement.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_rotation_matrix",
        "title": "G4RotationMatrix — Placement Rotation Type",
        "content": (
            "G4PVPlacement rotation arguments use G4RotationMatrix*. In Geant4, "
            "G4RotationMatrix is provided by G4RotationMatrix.hh and must be included when "
            "used in generated headers or sources. Do not forward declare "
            "class G4RotationMatrix because Geant4 may define it through an alias/type "
            "definition. Include: #include \"G4RotationMatrix.hh\". Use nullptr for no "
            "rotation and pass non-const G4RotationMatrix* to G4PVPlacement."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_nist_materials",
        "title": "G4NistManager — NIST Material Database",
        "content": (
            'G4NistManager::Instance()->FindOrBuildMaterial("G4_Si") returns a '
            "pre-defined NIST material. Common materials: G4_AIR, G4_Si, G4_Ge, "
            "G4_WATER, G4_COPPER, G4_ALUMINUM, G4_LEAD, G4_PLASTIC_SC_VINYLTOLUENE. "
            "Use FindOrBuildElement() for individual elements. "
            'Include: #include "G4NistManager.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_nist_material_names",
        "title": "Geant4 NIST Material Names — Common Pitfalls",
        "content": (
            "Common NIST material names include G4_AIR, G4_Galactic, G4_Si, "
            "G4_SILICON_DIOXIDE, G4_Al, G4_Cu, G4_W, G4_Pb, and G4_WATER. "
            "Use G4NistManager::Instance()->FindOrBuildMaterial(name) and check for null "
            "before using the material. Do not invent names such as G4_ALUMINUM when the "
            "model IR requests G4_Al. RadAgent material modules should map material_id and "
            "nist_name exactly from Model IR."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_custom_material",
        "title": "G4Material — Custom Material Definition",
        "content": (
            "G4Material(const G4String& name, G4double density, G4int nComponents, "
            "G4State state=kStateSolid) creates a custom material. Add elements via "
            "AddElement(G4Element*, G4int) or AddElement(G4Element*, G4double fraction). "
            "Density in g/cm3. For mixtures use fractional mass composition. "
            'Include: #include "G4Material.hh", #include "G4Element.hh", '
            '#include "G4SystemOfUnits.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_sensitive_detector",
        "title": "G4VSensitiveDetector — Sensitive Detector Base",
        "content": (
            "To create a sensitive detector, inherit from G4VSensitiveDetector. "
            "Override ProcessHits(G4Step* step, G4TouchableHistory* history) to "
            "extract energy deposition, position, and other step data. "
            "Override Initialize(G4HCofThisEvent*) to reset per-event data. "
            "Attach to logical volume: logicalVol->SetSensitiveDetector(sd). "
            "Hit collections are registered via G4THitsCollection. "
            'Include: #include "G4VSensitiveDetector.hh", #include "G4Step.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_particle_gun",
        "title": "G4ParticleGun — Primary Particle Generator",
        "content": (
            "G4ParticleGun(G4int numberofParticles=1) generates primary particles. "
            "Set particle definition: SetParticleDefinition(G4ParticleDefinition*). "
            "Set energy: SetParticleEnergy(G4double). "
            "Set position: SetParticlePosition(const G4ThreeVector&). "
            "Set direction: SetParticleMomentumDirection(const G4ThreeVector&). "
            "Must be called in GeneratePrimaries(G4Event*). "
            'Include: #include "G4ParticleGun.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_physics_list",
        "title": "G4VModularPhysicsList — Physics List",
        "content": (
            "Use G4VModularPhysicsList or FTFP_BERT, QGSP_BIC, Shielding for "
            "pre-built physics lists. EM physics: G4EmStandardPhysics (recommended). "
            "Hadronic: FTFP_BERT for protons/neutrons > 5 GeV. "
            "Register physics: RegisterPhysics(new G4EmStandardPhysics()). "
            'Include: #include "G4VModularPhysicsList.hh", '
            '#include "FTFP_BERT.hh" or #include "G4EmStandardPhysics.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_phys_list_factory",
        "title": "G4PhysListFactory — Reference Physics List Factory",
        "content": (
            "G4PhysListFactory creates Geant4 reference physics lists such as FTFP_BERT, "
            "QGSP_BERT, QGSP_BIC, and Shielding. Use "
            "factory.GetReferencePhysList(\"FTFP_BERT\") to obtain a G4VModularPhysicsList*. "
            "The factory object must remain valid while creating the list; do not return a "
            "physics list from a local temporary factory if the wrapper caches related state. "
            "Production cuts should be set on the physics list with SetDefaultCutValue(value) "
            "or SetCutValue(value, particleName) where supported by the actual physics-list API. "
            "Include: #include \"G4PhysListFactory.hh\" and #include \"G4VModularPhysicsList.hh\"."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_run_manager",
        "title": "G4RunManager — Simulation Execution",
        "content": (
            "G4RunManager manages the simulation lifecycle: "
            "SetUserInitialization(physicsList), SetUserInitialization(detectorConstruction), "
            "SetUserAction(primaryGeneratorAction), SetUserAction(runAction), "
            "SetUserAction(eventAction), SetUserAction(steppingAction). "
            "BeamOn(G4int numberOfEvents) starts the simulation. "
            "For multithreading use G4MTRunManager. "
            'Include: #include "G4RunManager.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_action_initialization",
        "title": "G4VUserActionInitialization — User Actions",
        "content": (
            "In modern Geant4 applications, derive ActionInitialization from "
            "G4VUserActionInitialization and override Build() const. Inside Build(), call "
            "SetUserAction(new PrimaryGeneratorAction(...)) and register optional RunAction, "
            "EventAction, or SteppingAction objects. main.cc should install actions with "
            "runManager->SetUserInitialization(new ActionInitialization(...)), not by calling "
            "SetUserAction directly from main when an ActionInitialization module owns runtime "
            "callbacks. Include: #include \"G4VUserActionInitialization.hh\"."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_run_macros",
        "title": "Geant4 Run Macros — Initialize Before BeamOn",
        "content": (
            "A Geant4 batch macro that starts events must initialize the kernel before "
            "beamOn. Put /run/initialize before /run/beamOn N. A minimal run.mac is: "
            "/run/initialize followed by /run/beamOn 1000. If BeamOn is called before "
            "initialization, Geant4 reports that the kernel should be initialized before "
            "the first BeamOn and ignores the run. Do not leave placeholder macro lines; "
            "macro files must contain real Geant4 UI commands or comments only."
        ),
        "source": "geant4_application_developers_guide",
    },
    {
        "doc_id": "g4_cmake_project",
        "title": "Minimal Geant4 CMake Project Contract",
        "content": (
            "A generated Geant4 CMakeLists.txt should call cmake_minimum_required, project, "
            "find_package(Geant4 REQUIRED ui_all vis_all), include(${Geant4_USE_FILE}) when "
            "using variable-style Geant4 CMake, add_executable(RadAgentG4 main.cc src/*.cc "
            "listed explicitly), target_include_directories(RadAgentG4 PRIVATE include), and "
            "target_link_libraries(RadAgentG4 ${Geant4_LIBRARIES}). Avoid file(GLOB) in "
            "acceptance code because cross-file gates require explicit source wiring."
        ),
        "source": "radagent_runtime_contract",
    },
    {
        "doc_id": "g4_step_energy_deposit",
        "title": "G4Step — Energy Deposition Access",
        "content": (
            "In ProcessHits, access energy deposit: step->GetTotalEnergyDeposit(). "
            "Position: step->GetPreStepPoint()->GetPosition(). "
            "Track ID: step->GetTrack()->GetTrackID(). "
            "Volume: step->GetPreStepPoint()->GetTouchable()->GetVolume(). "
            "Copy number: step->GetPreStepPoint()->GetTouchable()->GetCopyNumber(). "
            "Units: energy in MeV, position in mm (default Geant4 units). "
            'Include: #include "G4Step.hh".'
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_hits_collection",
        "title": "G4THitsCollection and G4Allocator — Hit Storage",
        "content": (
            "A sensitive detector commonly defines a Hit type and stores hits in "
            "G4THitsCollection<Hit>. Register hit collection names in the detector constructor "
            "with collectionName.push_back(\"CollectionName\"). In Initialize(G4HCofThisEvent*) "
            "create the hits collection and add it to the event HCE. Custom Hit allocation uses "
            "G4Allocator<Hit>::MallocSingle() in operator new and "
            "G4Allocator<Hit>::FreeSingle(static_cast<Hit*>(ptr)) in operator delete. "
            "Include: #include \"G4THitsCollection.hh\" and #include \"G4Allocator.hh\"."
        ),
        "source": "geant4_application_developers_guide",
    },
    {
        "doc_id": "g4_sensitive_detector_manager",
        "title": "G4SDManager — Register Sensitive Detectors",
        "content": (
            "Sensitive detectors are registered with "
            "G4SDManager::GetSDMpointer()->AddNewDetector(sd). "
            "Attach the detector to a logical volume with logicalVolume->SetSensitiveDetector(sd). "
            "If a helper AttachTo(G4LogicalVolume*) exists, it should call "
            "SetSensitiveDetector(this). "
            "Do not call nonexistent SetLogicalVolume on G4VSensitiveDetector. Include "
            "G4SDManager.hh and G4LogicalVolume.hh where needed."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_scoring_mesh_score_map",
        "title": "G4VScoringMesh — Score Map Access",
        "content": (
            "Command-based scoring meshes expose primitive scorer results through "
            "G4VScoringMesh::GetScoreMap(). The score map associates scorer names with "
            "G4THitsMap<G4StatDouble>* values. Use scoreMap.find(\"edepScorer\") or "
            "scoreMap.find(\"doseScorer\") on the score map, not on a hits map. To read a "
            "cell value, use hitsMap->GetObject(copyNo) and then G4StatDouble::sum_wx(), "
            "or inspect hitsMap->GetMap()->find(copyNo). Use "
            "G4ScoringManager::GetScoringManager() to access the scoring manager singleton; "
            "do not allocate G4ScoringManager with new. G4VScoringMesh does not provide "
            "GetNumberOfCells(); store the configured nBin values in ScoringManager and "
            "compute total cells as nBinsX * nBinsY * nBinsZ."
        ),
        "source": "geant4_scoring_documentation",
    },
    {
        "doc_id": "g4_logical_volume_complete_type",
        "title": "G4LogicalVolume — Complete Type Required for Member Access",
        "content": (
            "A forward declaration class G4LogicalVolume; is sufficient only for pointer "
            "or reference declarations. Any source file that calls logicalVolume->GetName(), "
            "logicalVolume->SetSensitiveDetector(...), or another G4LogicalVolume member "
            "must include the complete type header: #include \"G4LogicalVolume.hh\". "
            "PlacementManager.cc and SensitiveDetector.cc should include G4LogicalVolume.hh "
            "when they dereference G4LogicalVolume*."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_scoring_macros",
        "title": "Geant4 Command-Based Scoring Macro Commands",
        "content": (
            "Command-based scoring can create a mesh and primitive scorers with UI commands. "
            "Typical macro command groups are /score/create/boxMesh, /score/mesh/boxSize, "
            "/score/mesh/nBin, /score/quantity/energyDeposit, /score/quantity/doseDeposit, "
            "and /score/close. Generated code should not fake scoring output; scoring setup "
            "must correspond to actual scorers that OutputManager or ScoringManager reads."
        ),
        "source": "geant4_scoring_documentation",
    },
    {
        "doc_id": "g4_output_contract",
        "title": "RadAgent Geant4 Output Contract",
        "content": (
            "Generated Geant4 code must write runtime artifacts to the directory named by "
            "the G4_OUTPUT_DIR environment variable when it is set. OutputManager must write "
            "fixed filenames output.csv, run_summary.json, and metadata.json. Do not prefix "
            "these files with job ids such as job0_events.csv. output.csv must include the "
            "header EventID,edep_MeV,dose_Gy so Geant4Runner can materialize event_table.csv, "
            "edep_3d.csv, dose_3d.csv, g4_summary.json, and provenance.json."
        ),
        "source": "radagent_runtime_contract",
    },
    {
        "doc_id": "g4_run_event_actions_output",
        "title": "RunAction and EventAction — Runtime Output Hooks",
        "content": (
            "Output files are normally opened in BeginOfRunAction and closed in EndOfRunAction. "
            "Per-event rows can be written from EventAction or from a manager invoked by event "
            "callbacks. RadAgent's OutputManager contract requires output.csv, run_summary.json, "
            "and metadata.json under G4_OUTPUT_DIR. The generated code must create the output "
            "directory if needed or fail clearly; it must not silently write to the build "
            "directory when G4_OUTPUT_DIR is configured."
        ),
        "source": "radagent_runtime_contract",
    },
    {
        "doc_id": "g4_primary_generator_contract",
        "title": "G4VUserPrimaryGeneratorAction — GeneratePrimaries Contract",
        "content": (
            "PrimaryGeneratorAction must override GeneratePrimaries(G4Event* event). If the "
            "function body calls particleGun->GeneratePrimaryVertex(event), the parameter must "
            "be named event, not commented out as /*event*/ and not omitted. Include "
            "G4Event.hh, G4ParticleGun.hh, G4ParticleTable.hh, G4SystemOfUnits.hh, and "
            "G4ThreeVector.hh as needed."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_units",
        "title": "G4SystemOfUnits — Unit System",
        "content": (
            "Geant4 uses internal units: mm for length, MeV for energy, ns for time, "
            "g/cm3 for density. Use G4SystemOfUnits.hh to convert: "
            "mm, cm, m, km (length); eV, keV, MeV, GeV (energy); "
            "g/cm3, mg/cm3 (density); deg, rad (angle). "
            "Example: density = 2.33*g/cm3; energy = 100*MeV; length = 5*cm. "
            'Include: #include "G4SystemOfUnits.hh".'
        ),
        "source": "geant4_reference",
    },
]


class Geant4DocStore:
    """Provides Geant4 knowledge base documents for RAG indexing."""

    def get_documents(self) -> list[RAGDocument]:
        """Return all Geant4 reference documents."""
        return [
            RAGDocument(
                doc_id=d["doc_id"],
                title=d["title"],
                content=d["content"],
                source=d["source"],
            )
            for d in _G4_DOCUMENTS
        ]

    @staticmethod
    def get_document_count() -> int:
        """Return the number of documents in the store."""
        return len(_G4_DOCUMENTS)
