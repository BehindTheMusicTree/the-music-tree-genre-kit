from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CriteriaCoverageCounts:
    """A prepared count projection for one population and selection context."""

    genre_only_tracks_count: int
    genre_and_subgenres_tracks_count: int

    def __post_init__(self) -> None:
        values = (self.genre_only_tracks_count, self.genre_and_subgenres_tracks_count)
        if any(type(value) is not int or value < 0 for value in values) or values[0] > values[1]:
            raise ValueError("Coverage counts must be nonnegative integers with inclusive count at least exact count")
