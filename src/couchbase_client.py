"""
Couchbase connection wrapper for genetic algorithm data storage.

This module provides a clean interface to the Couchbase database that stores:
- unstructured: Source corpus chunks for compression tasks
- prompts: Individual prompts with lineage and evaluation results
- generations: Statistical summaries per generation
- eras: Experimental run configurations

The framework uses Couchbase because:
- JSON document storage matches our data model naturally
- N1QL queries enable phylogenetic analysis (Paper 2)
- Scales to large evolutionary runs (1000+ prompts)

Used by: GA operators, evaluation pipeline, analysis scripts
Creates: Complete lineage data for phylogenetic analysis
"""

import os
from typing import Optional, List, Dict, Any
from datetime import timedelta

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


class CouchbaseClient:
    """
    Manages connection to Couchbase cluster and provides collection access.

    This is a simple wrapper around the Couchbase Python SDK. It handles:
    - Connection establishment and management
    - Collection handle retrieval
    - Basic document operations (get, insert, upsert)
    - Connection cleanup

    Used throughout the framework for all database operations.

    Example:
        with CouchbaseClient() as cb:
            prompt_doc = cb.get_document("prompts", "prompt-uuid-123")
            cb.save_document("prompts", "new-uuid", new_prompt_dict)
    """

    def __init__(self):
        """
        Initialize Couchbase client with environment variable configuration.

        Required environment variables:
        - COUCHBASE_CONNECTION_STRING
        - COUCHBASE_USERNAME
        - COUCHBASE_PASSWORD
        - COUCHBASE_BUCKET (default: "genetic")
        - COUCHBASE_SCOPE (default: "g_scope")
        """
        self.connection_string = os.getenv("COUCHBASE_CONNECTION_STRING")
        self.username = os.getenv("COUCHBASE_USERNAME")
        self.password = os.getenv("COUCHBASE_PASSWORD")
        self.bucket_name = os.getenv("COUCHBASE_BUCKET", "genetic")
        self.scope_name = os.getenv("COUCHBASE_SCOPE", "g_scope")

        # Verify required credentials
        if not all([self.connection_string, self.username, self.password]):
            raise ValueError(
                "Missing required Couchbase credentials in .env file. "
                "Required: COUCHBASE_CONNECTION_STRING, COUCHBASE_USERNAME, COUCHBASE_PASSWORD"
            )

        self.cluster = None
        self.bucket = None
        self.scope = None

    def connect(self):
        """
        Establish connection to Couchbase cluster and bucket.

        Raises:
            Exception: If connection fails (fail loud, no fallback)
        """
        try:
            # Authenticate
            auth = PasswordAuthenticator(self.username, self.password)

            # Connect to cluster
            self.cluster = Cluster(
                self.connection_string,
                ClusterOptions(auth)
            )

            # Wait for cluster to be ready
            self.cluster.wait_until_ready(timedelta(seconds=10))

            # Get bucket and scope
            self.bucket = self.cluster.bucket(self.bucket_name)
            self.scope = self.bucket.scope(self.scope_name)

            print(f"✓ Connected to Couchbase: {self.bucket_name}/{self.scope_name}")

        except Exception as e:
            raise Exception(f"Failed to connect to Couchbase: {str(e)}")

    def get_collection(self, collection_name: str):
        """
        Get handle to a specific collection.

        Args:
            collection_name: Name of collection (unstructured|prompts|generations|eras)

        Returns:
            Couchbase collection handle

        Raises:
            Exception: If not connected or collection doesn't exist
        """
        if not self.scope:
            raise Exception("Not connected to Couchbase. Call connect() first.")

        try:
            return self.scope.collection(collection_name)
        except Exception as e:
            raise Exception(f"Failed to get collection '{collection_name}': {str(e)}")

    def get_document(self, collection_name: str, document_id: str) -> Dict[str, Any]:
        """
        Retrieve a document from a collection.

        Args:
            collection_name: Collection to query
            document_id: Document ID to retrieve

        Returns:
            Document content as dictionary

        Raises:
            Exception: If document not found or retrieval fails
        """
        try:
            collection = self.get_collection(collection_name)
            result = collection.get(document_id)
            return result.content_as[dict]
        except Exception as e:
            raise Exception(
                f"Failed to get document '{document_id}' from '{collection_name}': {str(e)}"
            )

    def save_document(self, collection_name: str, document_id: str, content: Dict[str, Any]):
        """
        Save (upsert) a document to a collection.

        Args:
            collection_name: Collection to save to
            document_id: Document ID (will overwrite if exists)
            content: Document content as dictionary

        Raises:
            Exception: If save fails
        """
        try:
            collection = self.get_collection(collection_name)
            collection.upsert(document_id, content)
        except Exception as e:
            raise Exception(
                f"Failed to save document '{document_id}' to '{collection_name}': {str(e)}"
            )

    def close(self):
        """Close cluster connection."""
        if self.cluster:
            self.cluster.close()
            print("✓ Couchbase connection closed")

    def __enter__(self):
        """Context manager entry - connect automatically."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connection."""
        self.close()
