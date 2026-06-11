// Hit.hh
// Hit data structure for storing sensitive detector measurements
// Stores energy deposition and position for silicon detector scoring

#ifndef HIT_HH
#define HIT_HH

#include "G4VHit.hh"
#include "G4THitsCollection.hh"
#include "G4Allocator.hh"
#include "G4ThreeVector.hh"
#include "G4SystemOfUnits.hh"
#include "globals.hh"

class Hit : public G4VHit
{
public:
    Hit() = default;
    Hit(const Hit&) = default;
    ~Hit() override = default;

    Hit& operator=(const Hit&) = default;
    G4bool operator==(const Hit&) const;

    inline void* operator new(size_t);
    inline void operator delete(void*);

    // Methods from base class
    void Draw() override;
    void Print() override;

    // Setters
    void SetTrackID(G4int trackId) { fTrackID = trackId; }
    void SetEdep(G4double edep) { fEdep = edep; }
    void SetPos(const G4ThreeVector& pos) { fPos = pos; }
    void SetLocalPos(const G4ThreeVector& pos) { fLocalPos = pos; }

    // Getters
    G4int GetTrackID() const { return fTrackID; }
    G4double GetEdep() const { return fEdep; }
    const G4ThreeVector& GetPos() const { return fPos; }
    const G4ThreeVector& GetLocalPos() const { return fLocalPos; }

private:
    G4int fTrackID = 0;
    G4double fEdep = 0.0;
    G4ThreeVector fPos;
    G4ThreeVector fLocalPos;
};

using HitsCollection = G4THitsCollection<Hit>;

extern G4ThreadLocal G4Allocator<Hit>* HitAllocator;

inline void* Hit::operator new(size_t)
{
    if (!HitAllocator)
        HitAllocator = new G4Allocator<Hit>;
    return (void*)HitAllocator->MallocSingle();
}

inline void Hit::operator delete(void* hit)
{
    HitAllocator->FreeSingle((Hit*)hit);
}

#endif // HIT_HH