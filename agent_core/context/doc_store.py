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
            "world volumes and layer geometries. Include: #include \"G4Box.hh\". "
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
            "Include: #include \"G4Tubs.hh\"."
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
            "Include: #include \"G4Sphere.hh\"."
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
            "Include: #include \"G4Trap.hh\"."
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
            "Include: #include \"G4Polycone.hh\"."
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
            "SetSensitiveDetector(). Include: #include \"G4LogicalVolume.hh\"."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_physical_volume",
        "title": "G4PVPlacement — Physical Volume Placement",
        "content": (
            "G4PVPlacement(G4RotationMatrix* pRot, const G4ThreeVector& pTrans, "
            "const G4String& pName, G4LogicalVolume* pLogical, "
            "G4VPhysicalVolume* pMother, G4bool pMany, G4int pCopyNo, "
            "G4bool pOverlaps=false) places a logical volume inside a mother volume. "
            "Position and rotation are in the mother's coordinate system. "
            "The world volume has no mother (nullptr). Set pOverlaps=true to enable "
            "overlap checking. Include: #include \"G4PVPlacement.hh\"."
        ),
        "source": "geant4_reference",
    },
    {
        "doc_id": "g4_nist_materials",
        "title": "G4NistManager — NIST Material Database",
        "content": (
            "G4NistManager::Instance()->FindOrBuildMaterial(\"G4_Si\") returns a "
            "pre-defined NIST material. Common materials: G4_AIR, G4_Si, G4_Ge, "
            "G4_WATER, G4_COPPER, G4_ALUMINUM, G4_LEAD, G4_PLASTIC_SC_VINYLTOLUENE. "
            "Use FindOrBuildElement() for individual elements. "
            "Include: #include \"G4NistManager.hh\"."
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
            "Include: #include \"G4Material.hh\", #include \"G4Element.hh\", "
            "#include \"G4SystemOfUnits.hh\"."
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
            "Include: #include \"G4VSensitiveDetector.hh\", #include \"G4Step.hh\"."
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
            "Include: #include \"G4ParticleGun.hh\"."
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
            "Include: #include \"G4VModularPhysicsList.hh\", "
            "#include \"FTFP_BERT.hh\" or #include \"G4EmStandardPhysics.hh\"."
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
            "Include: #include \"G4RunManager.hh\"."
        ),
        "source": "geant4_reference",
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
            "Include: #include \"G4Step.hh\"."
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
            "Include: #include \"G4SystemOfUnits.hh\"."
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
