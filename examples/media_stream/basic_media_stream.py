from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import ArtifactLineage, EvidenceExporter, MediaMetadata, Runtime, StreamChunkRef


async def media_agent(ctx: Any, _state: dict[str, Any]) -> None:
    frame_id = await ctx.create_media_artifact(
        "frame-0001",
        "frame",
        uri="s3://media/demo/frame-0001.jpg",
        media_metadata=MediaMetadata(
            kind="frame",
            mime_type="image/jpeg",
            width=1280,
            height=720,
            timestamp_start_seconds=1.5,
            frame_index=1,
        ),
        lineage=ArtifactLineage(source_blob_refs=["s3://media/demo/input.mp4"], tool_call_ids=["video.extract_frames"]),
    )
    checkpoint_id = await ctx.create_stream_checkpoint(
        "camera-checkpoint",
        stream_id="camera-1",
        consumer_id="vision-agent",
        offset=7,
        watermark=1.5,
        chunk=StreamChunkRef(stream_id="camera-1", chunk_id="chunk-7", offset=7, content_ref="blob://sha256/chunk-7.json", sequence=7),
        partial_result_ref="blob://sha256/partial-vision-result.json",
        backpressure={"recommended_pause_ms": 100},
    )
    ctx.write_state_patch("artifacts", {"frame": frame_id, "checkpoint": checkpoint_id})


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(media_agent, run_id=run_id, agent_role="MediaAgent")
        evidence = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
        print(
            json.dumps(
                {
                    "ok": ok,
                    "run_id": run_id,
                    "state": rt.store.final_state(run_id),
                    "summary": evidence["summary"],
                    "media_artifacts": evidence["media_artifacts"],
                    "stream_checkpoints": evidence["stream_checkpoints"],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
