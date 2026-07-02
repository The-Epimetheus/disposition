"""One place that persists what Capture produces.

Every Capture path -- bootstrap, interview, ambient, correction -- ends the same
way: it has a batch of new Exemplars and/or Rules and has to fold them into the
Store. That tail was copy-pasted four times: load the current Exemplars, add the
new ones (deduped by content id), count how many were actually new, rebuild the
vector index, merge the Rules. This module is that tail, written once.

The pieces it coordinates are the Capture primitives. An Exemplar is a stored
piece of real code; a Rule is a legible statement of taste; the vector index is
a derived cache over the Exemplars, not a source of truth. Because it is derived,
we hold one invariant: whenever the stored Exemplars change, the index is rebuilt
so it always reflects them. We even rebuild when a batch dedups down to zero new
Exemplars, so the reported index size is honest rather than a stale guess. When a
call brings no Exemplars at all we leave the index untouched and just report its
current size, because there is nothing new for it to reflect.

Everything targets the Language layer, matching what the callers did by hand.
The embedder is whatever the caller injects, or the one config names (the
offline hash by default, the semantic model when opted in).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..index import VectorIndex
from ..models import Exemplar, Layer, Rule


@dataclass
class CaptureCounts:
    """What one capture() call persisted, for the caller to report."""

    exemplars_added: int
    rules_added: int
    index_size: int


class CapturePipeline:
    """Folds new Exemplars and Rules into the Store for one language."""

    def __init__(self, store, language: str = "java", *, embedder=None):
        self.store = store
        self.language = language
        self.embedder = embedder

    def capture(
        self,
        exemplars: list[Exemplar] | None = None,
        rules: list[Rule] | None = None,
    ) -> CaptureCounts:
        """Persist the given Exemplars and Rules, returning the counts.

        Exemplars are added deduped by id and the index is rebuilt so it always
        reflects the stored Exemplars (even when the batch dedups to zero). With
        no Exemplars the index is left alone and its current size is reported.
        Rules are merged newest-wins; an empty batch merges nothing.
        """
        if exemplars:
            before = len(self.store.load_exemplars(Layer.LANGUAGE, self.language))
            self.store.add_exemplars(Layer.LANGUAGE, exemplars, self.language)
            after = len(self.store.load_exemplars(Layer.LANGUAGE, self.language))
            exemplars_added = after - before
            index_size = self.store.rebuild_index(
                Layer.LANGUAGE, self.language, embedder=self.embedder
            )
        else:
            exemplars_added = 0
            index_size = self._current_index_size()

        rules_added = self.store.merge_rules(
            Layer.LANGUAGE, rules or [], self.language
        )
        return CaptureCounts(
            exemplars_added=exemplars_added,
            rules_added=rules_added,
            index_size=index_size,
        )

    def _current_index_size(self) -> int:
        """Size of the already-built index, or 0 if none has been built yet."""
        index_dir = self.store.index_dir(Layer.LANGUAGE, self.language)
        if VectorIndex.exists(index_dir):
            return len(VectorIndex.load(index_dir))
        return 0
