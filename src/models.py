"""
Data models for genetic algorithm prompt optimization.

This module defines the core data structures used throughout the framework:
- PromptTag: Individual tags that can mutate and evolve
- Prompt: Complete prompt with 5 tags + evaluation results

These models are used by:
- Couchbase storage/retrieval (to_dict/from_dict)
- GA operators (mutation, crossover, selection)
- Fitness evaluation pipeline
- Phylogenetic analysis (Paper 2)

Critical: Lineage tracking fields (parent_tag_guid, parents) enable
phylogenetic tree construction and are required for research goals.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from uuid import uuid4


@dataclass
class PromptTag:
    """
    Represents a single tag within a prompt.

    Tags are the atomic units of evolution. Each of the 5 tags (role,
    compression_target, fidelity, constraints, output) can be:
    - Mutated: New text, new guid, parent_tag_guid = old guid
    - Crossed over: Copied from parent, same guid, parent_tag_guid = old parent
    - Created fresh: Initial/immigrant with no parent

    The guid enables tracking tag lineage across generations, critical for
    phylogenetic analysis in Paper 2.

    Lineage Fields:
    - source: How tag entered THIS prompt (operator used: "initial" | "mutation" | "crossover" | "immigrant")
    - origin: How tag was FIRST CREATED (never changes: "initial" | "mutation" | "immigrant")

    Note: source changes as tag flows through population, origin never changes for a given guid.

    Used by: Prompt, GA operators (mutation/crossover), lineage analysis
    """

    guid: str = field(default_factory=lambda: str(uuid4()))
    text: str = ""
    parent_tag_guid: Optional[str] = None
    source: str = "initial"  # "initial" | "mutation" | "crossover" | "immigrant"
    origin: str = "initial"  # "initial" | "mutation" | "immigrant" (never "crossover")

    def to_dict(self) -> Dict:
        """Convert to dictionary for Couchbase storage."""
        return {
            "guid": self.guid,
            "text": self.text,
            "parent_tag_guid": self.parent_tag_guid,
            "source": self.source,
            "origin": self.origin
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PromptTag':
        """Reconstruct PromptTag from Couchbase document."""
        return cls(
            guid=data["guid"],
            text=data["text"],
            parent_tag_guid=data.get("parent_tag_guid"),
            source=data.get("source", "initial"),
            origin=data.get("origin", data.get("source", "initial"))  # Backward compat: default origin to source
        )


@dataclass
class Prompt:
    """
    Represents a complete prompt with 5 tags and evaluation results.

    This is the core unit of evolution. Each prompt:
    - Contains 5 PromptTag objects (role, compression_target, fidelity,
      constraints, output)
    - Tracks which LLM generated it (model_used)
    - Records lineage via parents array
    - Stores evaluation results (fitness, compression metrics, quality scores)

    Lineage tracking enables:
    - Building phylogenetic trees (parents array)
    - Identifying successful evolutionary paths
    - Analyzing which mutations led to fitness improvements

    Used by: GeneticAlgorithm, CouchbaseClient, EvaluationPipeline,
             AnalysisPipeline (Paper 2)
    Creates: Generation statistics, lineage data for phylogenetic analysis
    """

    # Identity
    prompt_id: str = field(default_factory=lambda: str(uuid4()))
    generation: int = 0
    era: str = ""

    # Lineage tracking (critical for Paper 2)
    type: str = "initial"  # "initial" | "mutation" | "crossover" | "immigrant"
    parents: Optional[List[str]] = None  # parent prompt_id(s)
    model_used: str = ""  # "openai" | "claude" | "gemini"

    # Source data
    source_paragraph_id: Optional[str] = None

    # Tags (the evolvable components)
    role: Optional[PromptTag] = None
    compression_target: Optional[PromptTag] = None
    fidelity: Optional[PromptTag] = None
    constraints: Optional[PromptTag] = None
    output: Optional[PromptTag] = None

    # Evaluation results (populated during fitness evaluation)
    original_text: Optional[str] = None
    compressed_text: Optional[str] = None
    original_words: Optional[int] = None
    compressed_words: Optional[int] = None
    compression_ratio: Optional[float] = None  # word-based for backward compatibility
    original_tokens: Optional[int] = None  # Token-based metrics (NEW)
    compressed_tokens: Optional[int] = None
    token_compression_ratio: Optional[float] = None
    quality_scores: Optional[Dict[str, float]] = None  # {"openai": 8.5, "claude": 7.2, "gemini": 8.8}
    quality_score_avg: Optional[float] = None
    survival_factor: Optional[int] = None  # 0 if expanded, 1 if compressed
    fitness: Optional[float] = None

    def to_dict(self) -> Dict:
        """
        Convert to dictionary for Couchbase storage.

        Returns complete document including all tags and evaluation results.
        Used by CouchbaseClient.save_prompt().
        """
        doc = {
            "prompt_id": self.prompt_id,
            "generation": self.generation,
            "era": self.era,
            "type": self.type,
            "parents": self.parents,
            "model_used": self.model_used,
            "source_paragraph_id": self.source_paragraph_id,
        }

        # Add tags
        if self.role:
            doc["role"] = self.role.to_dict()
        if self.compression_target:
            doc["compression_target"] = self.compression_target.to_dict()
        if self.fidelity:
            doc["fidelity"] = self.fidelity.to_dict()
        if self.constraints:
            doc["constraints"] = self.constraints.to_dict()
        if self.output:
            doc["output"] = self.output.to_dict()

        # Add evaluation results (if populated)
        if self.original_text is not None:
            doc["original_text"] = self.original_text
        if self.compressed_text is not None:
            doc["compressed_text"] = self.compressed_text
        if self.original_words is not None:
            doc["original_words"] = self.original_words
        if self.compressed_words is not None:
            doc["compressed_words"] = self.compressed_words
        if self.compression_ratio is not None:
            doc["compression_ratio"] = self.compression_ratio
        if self.original_tokens is not None:
            doc["original_tokens"] = self.original_tokens
        if self.compressed_tokens is not None:
            doc["compressed_tokens"] = self.compressed_tokens
        if self.token_compression_ratio is not None:
            doc["token_compression_ratio"] = self.token_compression_ratio
        if self.quality_scores is not None:
            doc["quality_scores"] = self.quality_scores
        if self.quality_score_avg is not None:
            doc["quality_score_avg"] = self.quality_score_avg
        if self.survival_factor is not None:
            doc["survival_factor"] = self.survival_factor
        if self.fitness is not None:
            doc["fitness"] = self.fitness

        return doc

    @classmethod
    def from_dict(cls, data: Dict) -> 'Prompt':
        """
        Reconstruct Prompt from Couchbase document.

        Used by CouchbaseClient.get_prompt() and query results.
        """
        # Build tags
        role = PromptTag.from_dict(data["role"]) if "role" in data else None
        compression_target = PromptTag.from_dict(data["compression_target"]) if "compression_target" in data else None
        fidelity = PromptTag.from_dict(data["fidelity"]) if "fidelity" in data else None
        constraints = PromptTag.from_dict(data["constraints"]) if "constraints" in data else None
        output = PromptTag.from_dict(data["output"]) if "output" in data else None

        return cls(
            prompt_id=data["prompt_id"],
            generation=data["generation"],
            era=data["era"],
            type=data.get("type", "initial"),
            parents=data.get("parents"),
            model_used=data.get("model_used", ""),
            source_paragraph_id=data.get("source_paragraph_id"),
            role=role,
            compression_target=compression_target,
            fidelity=fidelity,
            constraints=constraints,
            output=output,
            original_text=data.get("original_text"),
            compressed_text=data.get("compressed_text"),
            original_words=data.get("original_words"),
            compressed_words=data.get("compressed_words"),
            compression_ratio=data.get("compression_ratio"),
            original_tokens=data.get("original_tokens"),
            compressed_tokens=data.get("compressed_tokens"),
            token_compression_ratio=data.get("token_compression_ratio"),
            quality_scores=data.get("quality_scores"),
            quality_score_avg=data.get("quality_score_avg"),
            survival_factor=data.get("survival_factor"),
            fitness=data.get("fitness")
        )
