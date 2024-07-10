from __future__ import annotations
import site
import numpy as np
import numpy.typing as npt

from collections import defaultdict
import itertools

__all__ = [
    "World",
    "Species",
    "Occupant",
    "Hop",
    "BirthReaction",
    "DeathReaction",
    "PredationReaction",
    "PredationBirthReaction",
]


class Species:
    """Defines a species."""

    def __init__(self, name: str):
        """Initialize a new species. Takes the `name` of the species as an argument (needs to be unique!)."""
        self.name: str = name
        self.members: list[Occupant] = []
        self._hash = hash(name)

    def add(self, occupant: Occupant):
        """Add a new `occupant` to this species."""
        assert occupant.species == self
        occupant._species_index = len(self.members)
        self.members.append(occupant)

    def remove(self, occupant: Occupant):
        """Remove an `occupant` from this species (i.e. the occupant dies)."""
        index: int = occupant._species_index
        end: Occupant = self.members.pop()
        if end._species_index != index:
            self.members[index] = end
            end._species_index = index

    def __hash__(self):
        return self._hash

    def __len__(self):
        return len(self.members)

    def __str__(self):
        return self.name


class Site:
    """Describes a lattice site."""

    def __init__(self, id):
        """Initialize a new lattice site with a unique `id`."""
        self.id = id
        self.species_occupants: dict[Species, list[Occupant]] = defaultdict(list)
        self.neighbors: list[Site] = []

    def species_abundance(self, species: Species) -> int:
        """Returns the abundance of the given `species` at this lattice site."""
        return len(self.species_occupants[species])

    def get_random_occupant(
        self, species: Species, rng: np.random.Generator
    ) -> Occupant:
        """Return a random occupant of the given `species`. The random number generator used needs to be given as `rng`."""
        occupant_list = self.species_occupants[species]
        number = len(occupant_list)
        if number == 0:
            return None
        return occupant_list[rng.integers(number)]

    def add(self, occupant: Occupant):
        """Add an `occupant` to this lattice site."""
        occupants: list[Occupant] = self.species_occupants[occupant.species]
        occupant._site_index = len(occupants)
        occupants.append(occupant)

    def remove(self, occupant: Occupant):
        """Remove the given `occupant` from this lattice site. Note that for performance reasons no checking is performed if this occupant is actually present at this site - if not this will lead to corruption!"""
        index: int = occupant._site_index
        occupants: list[Occupant] = self.species_occupants[occupant.species]
        other: Occupant = occupants.pop()
        if other._site_index != index:
            occupants[index] = other
            other._site_index = index

    def __str__(self):
        return str(self.id)


# Internal counter to give unique IDs to occupants.
occupant_counter = itertools.count()


class Occupant:
    """Describes a lattice site occupant."""

    _site_index: int
    _species_index: int

    def __init__(self, species: Species, initial_site: Site):
        """Initialize a new site occupant of the given `species` at the `initial_site`."""
        self.id = next(occupant_counter)

        self.species = species
        self.species.add(self)
        self.site = initial_site
        self.site.add(self)

    def destroy(self):
        """Destroys the occupant. Removes it from its current lattice site and from the global species list."""
        self.species.remove(self)
        self.site.remove(self)

    def set_site(self, site: Site):
        """Moves the occupant to a new `site`. Removes it from the old site."""
        self.site.remove(self)
        site.add(self)
        self.site = site

    def __hash__(self):
        return self.id

    def __str__(self):
        return f"{self.species.name}{self.id}"


class Lattice:
    """Describes a 2D lattice."""

    def __init__(self, size: tuple[int, int]):
        """Initialize a lattice with the given `size` (e.g. 256x256 sites)."""
        self.size: tuple[int, int] = size
        self.nr_sites = self.size[0] * self.size[1]
        # Linear list of sites, where the site IDs are given as the xy index coordinates.
        self.sites: list[Site] = [
            Site(f"{i}x{j}") for i in range(size[0]) for j in range(size[1])
        ]
        i: int
        site: Site
        # Iterate over all sites and assign neighbor sites.
        for i, site in enumerate(self.sites):
            x = i % size[0]
            y = i // size[0]
            if x == 0:
                site.neighbors.append(self.sites[i + size[0] - 1])
            else:
                site.neighbors.append(self.sites[i - 1])
            if x == size[0] - 1:
                site.neighbors.append(self.sites[i - size[0] + 1])
            else:
                site.neighbors.append(self.sites[i + 1])

            if y == 0:
                site.neighbors.append(self.sites[size[0] * (size[1] - 1) + x])
            else:
                site.neighbors.append(self.sites[(y - 1) * size[0] + x])
            if y == size[1] - 1:
                site.neighbors.append(self.sites[x])
            else:
                site.neighbors.append(self.sites[(y + 1) * size[0] + x])


class Reaction:
    """Base class describing a reaction. Has to be subclassed."""

    def __init__(self, rate: float):
        """Initialize reaction with the given `rate`."""
        self.rate = rate

    def decide(self, rng: np.random.Generator):
        """Decide if the reaction takes place by generating a random number from the generator `rng`."""
        return (self.rate >= 1.0) or (rng.random() < self.rate)

    def __call__(self, occupant: Occupant, rng: np.random.Generator) -> bool:
        """Decides if reaction will be performed and if yes performs the reaction - needs to be overridden by the subclass' method. Needs to return `True` if the `occupant` was destroyed."""
        raise NotImplementedError


class BirthReaction(Reaction):
    """Describes an occupant birth reaction (A->2A)."""

    def __init__(self, species: Species, rate: float):
        """Initialize a birth reaction of `species` with the given `rate`."""
        self.species: Species = species
        super().__init__(rate)

    def __call__(self, occupant: Occupant, rng: np.random.Generator) -> bool:
        """Decides if birth reaction occurs for the given `occupant` (using the random generator `rng`) and if yes, generates a new occupant of the same species at the `occupant`'s site. Returns `False` because the `occupant` will never be destroyed in a birth reaction."""
        if self.decide(rng):
            new_occupant = Occupant(occupant.species, occupant.site)
        return False


class DeathReaction(Reaction):
    """Describes an occupant death reaction (A->0)."""

    def __init__(self, species: Species, rate: float):
        """Initialize a death reaction of `species` with the given `rate`."""
        self.species: Species = species
        super().__init__(rate)

    def __call__(self, occupant: Occupant, rng: np.random.Generator) -> bool:
        """Decides if death reaction occurs for the given `occupant` (using the random generator `rng`) and if yes, destroys the `occupant`. Returns `True` if the `occupant` was destroyed, `False` otherwise."""
        if self.decide(rng):
            occupant.destroy()
            return True
        return False


class PredationReaction(Reaction):
    """Describes an occupant predation reaction (A+B->A)."""

    def __init__(self, speciesA: Species, speciesB: Species, rate: float):
        """Initialize a predation reaction of `speciesA` (predator) and `speciesB` (prey) with the given `rate`."""
        self.speciesA: Species = speciesA
        self.speciesB: Species = speciesB
        super().__init__(rate)

    def __call__(self, occupant: Occupant, rng: np.random.Generator) -> bool:
        """For each victim of `speciesB` on the `occupant`'s lattice site, decides if predation reaction occurs. If yes, destroys the `speciesB` victim. Returns `False` because the predation reaction never destroys the original `occupant`."""
        site: Site = occupant.site
        # Need to collect victims that should be destroyed and destroy them later.
        # Otherwise the list we are iterating over will change during iteration!
        to_destroy = []
        for victim in site.species_occupants[self.speciesB]:
            if self.decide(rng):
                to_destroy.append(victim)
        for victim in to_destroy:
            victim.destroy()

        return False


class PredationBirthReaction(Reaction):
    """Describes an occupant predation-birth reaction (A+B->2A)."""

    def __init__(self, speciesA: Species, speciesB: Species, rate: float):
        """Initialize a predation-birth reaction of `speciesA` (predator) and `speciesB` (prey) with the given `rate`."""
        self.speciesA: Species = speciesA
        self.speciesB: Species = speciesB
        super().__init__(rate)

    def __call__(self, occupant: Occupant, rng: np.random.Generator) -> bool:
        """For each victim of `speciesB` on the `occupant`'s lattice site, decides if predation reaction occurs. If yes, destroys the `speciesB` victim and creates a new occupant of `speciesA`. Returns `False` because the predation reaction never destroys the original `occupant`."""
        site: Site = occupant.site
        # Need to collect victims that should be destroyed and destroy them later.
        # Otherwise the list we are iterating over will change during iteration!
        to_destroy = []
        for victim in site.species_occupants[self.speciesB]:
            if self.decide(rng):
                to_destroy.append(victim)
        for victim in to_destroy:
            victim.destroy()
            new_occupant = Occupant(occupant.species, site)

        return False


class Hop(Reaction):
    """Describes an occupant hop reaction between sites."""

    def __init__(self, species: Species, rate: float):
        """Initialize a hop reaction of the given `species` and with the given `rate`."""
        self.species: Species = species
        super().__init__(rate)

    def __call__(self, occupant: Occupant, destination_index):
        """Hop the given `occupant` from its original site to the site with neighbor index `destination_index` (between 0 and 3 inclusive)."""
        destination: Site = occupant.site.neighbors[destination_index]
        occupant.set_site(destination)


class World:
    """Describes the world in which the simulation takes place."""

    def __init__(
        self,
        size: tuple[int, int],
        initial_densities: dict[Species, float],
        hops: dict[Species, Hop],
        reactions: dict[Species, list[Reaction]],
        seed=None,
    ):
        """Initialize a world of the given `size` (e.g. 256x256), with the given `initial_densities`, hop reactions `hops` and inter-occupant `reactions`. Optionally the initial random `seed` can be specified."""
        self.lattice: Lattice = Lattice(size)
        density_species = set(initial_densities.keys())
        hop_species = set(hops.keys())
        reaction_species = set(reactions.keys())
        self.species: list[Species] = list(
            set.union(density_species, hop_species, reaction_species)
        )

        self.hops: dict[Species, Hop] = hops
        self.reactions: dict[Species, Reaction] = reactions

        self.random_generator = np.random.default_rng(seed=seed)

        self.initialization(initial_densities)

    def initialization(self, densities: dict[Species, float]):
        """Seed the initial occupants on the lattice."""
        for site in self.lattice.sites:
            for species, density in densities.items():
                for _ in range(self.random_generator.poisson(density)):
                    Occupant(species, site)

    def iteration(self):
        """Perform one iteration (part of a step)."""
        # Find how many occupants of each species there are currently on the lattice.
        members_per_species = [len(species) for species in self.species]
        # Find the total number of occupants of all species.
        total = sum(members_per_species)
        # Select one of them at random by generating a random index.
        selected_index = self.random_generator.integers(total)
        # Find the occupant with this index
        for N, species in zip(members_per_species, self.species):
            if selected_index < N:
                occupant: Occupant = species.members[selected_index]
                break
            selected_index -= N

        # Let the occupant hop to a neighboring site.
        species: Species = occupant.species
        if species in self.hops:
            self.hops[species](occupant, self.random_generator.integers(4))

        # Perform all reactions for the given occupant
        reaction: Reaction
        for reaction in self.reactions[species]:
            # If the occupant is destroyed during a reaction, exit the loop.
            if reaction(occupant, self.random_generator):
                break

    def step(self):
        """Perform one Monte Carlo step. A step is defined as performing N iterations where N is the current number of occupants on the lattice."""
        members_per_species = [len(species) for species in self.species]
        total = sum(members_per_species)
        for _ in range(total):
            self.iteration()

    def run(self, number_steps: int, progress_wrap=None):
        """Run the simulation for `number_of_steps`. Optionally a `progress_wrap` function can be passed in to display a progress bar."""
        if progress_wrap is None:
            progress_wrap = lambda iterator: iterator
        for _ in progress_wrap(range(number_steps)):
            self.step()

    @property
    def abundances(self) -> dict[Species, int]:
        """The abundance of all species occupants on the lattice."""
        return {species.name: len(species) for species in self.species}

    def asarrays(self) -> dict[str, npt.ArrayLike]:
        """Return the current abundances of all species on each lattice site as arrays."""
        return {
            species.name: np.array(
                [site.species_abundance(species) for site in self.lattice.sites]
            ).reshape(self.lattice.size)
            for species in self.species
        }
