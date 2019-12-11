__authors__ = "Johannes Köster, Sven Nahnsen"
__copyright__ = "Copyright 2019, Johannes Köster, Sven Nahnsen"
__email__ = "johannes.koester@uni-due.de"
__license__ = "MIT"


import hashlib
import json

from snakemake.jobs import Job

# ATTENTION: increase version number whenever the hashing algorithm below changes!
__version__ = "0.1"


class ProvenanceHashMap:
    def __init__(self):
        self._hashes = dict()

    def get_provenance_hash(self, job: Job):
        versioned_hash = hashlib.sha256()
        # Ensure that semantic version changes in this module
        versioned_hash.update(self._get_provenance_hash(job).encode())
        versioned_hash.update(__version__.encode())
        return versioned_hash.hexdigest()

    def _get_provenance_hash(self, job: Job):
        """
        Recursively calculate hash for the single output file of the given job
        and all upstream jobs in a blockchain fashion.

        This is based on an idea of Sven Nahnsen.
        Fails if job has more than one output file. The reason is that there
        is no way to generate a per-output file hash without generating the files.
        This hash, however, shall work without having to generate the files,
        just by describing all steps down to a given job.
        """
        if job in self._hashes:
            return self._hashes[job]

        if len(job.output) > 1:
            raise WorkflowError(
                "Cannot generate hash for rule {}: it has more than one output file.".format(
                    job.rule.name
                )
            )

        workflow = job.dag.workflow
        h = hashlib.sha256()

        # Hash shell command or script.
        if job.is_shell:
            # We cannot use the formatted shell command, because it also contains threads,
            # resources, and filenames (which shall be irrelevant for the hash).
            h.update(job.rule.shellcmd.encode())
        elif job.is_script:
            _, source, _ = script.get_source(job.rule.script)
            h.update(source.encode())
        elif job.is_wrapper:
            _, source, _ = script.get_source(
                wrapper.get_script(job.rule.wrapper, prefix=workflow.wrapper_prefix)
            )
            h.update(source.encode())

        # Hash params.
        for key, value in sorted(job.params._allitems()):
            h.update(key.encode())
            # If this raises a TypeError, we cannot calculate a reliable hash.
            h.update(json.dumps(value, sort_keys=True).encode())

        # Hash input files that are not generated by other jobs.
        for f in job.input:
            if not any(
                f in depfiles for depfiles in job.dag.dependencies[job].values()
            ):
                with open(f, "b") as f:
                    # Read and update hash string value in blocks of 4K
                    for byte_block in iter(lambda: f.read(4096), b""):
                        h.update(byte_block)

        # Hash used containers or conda environments.
        if workflow.use_conda and job.conda_env:
            if workflow.use_singularity and job.conda_env.singularity_img_url:
                h.update(job.conda_env.singularity_img_url.encode())
            h.update(job.conda_env.content.encode())
        elif workflow.use_singularity and job.singularity_img_url:
            h.update(job.singularity_img_url.encode())

        # Generate hashes of dependencies, and add them in a blockchain fashion (as input to the current hash).
        for dep_hash in sorted(
            self._get_provenance_hash(dep)
            for dep in set(job.dag.dependencies[job].keys())
        ):
            h.update(dep_hash.encode())

        provenance_hash = h.hexdigest()

        # Store for re-use.
        self._hashes[job] = provenance_hash

        return provenance_hash
