#ifndef PhysicsListFactoryWrapper_h
#define PhysicsListFactoryWrapper_h 1

#include "G4VUserPhysicsList.hh"

/// Factory wrapper that creates and configures the physics list
/// based on G4ModelIR physics requirements.
/// Returns a pointer to a physics list suitable for the specified
/// particle, energy range and scoring needs.

class PhysicsListFactoryWrapper
{
public:
  PhysicsListFactoryWrapper();
  ~PhysicsListFactoryWrapper();

  /// Create and return a physics list configured for the simulation.
  /// Caller takes ownership of the returned pointer.
  G4VUserPhysicsList* CreatePhysicsList();

private:
  // No data members - factory is stateless
};

#endif
