from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import ArtifactLineage, EvidenceExporter, MediaMetadata, Runtime, register_media_tool_conventions


def fake_extract_frames(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_refs": [
            {
                "uri": "s3://media/demo/frame-0001.jpg",
                "frame_index": 1,
                "timestamp_start_seconds": 1.5,
            }
        ],
        "timeline_ref": "blob://sha256/timeline.json",
        "metadata": {"source_ref": args["source_ref"]},
    }


async def media_tool_agent(ctx: Any, _state: dict[str, Any]) -> None:
    result = await ctx.call_tool(
        "video.extract_frames",
        {
            "source_ref": "s3://media/demo/input.mp4",
            "max_frames": 1,
            "_logical_operation": "demo-frame-extraction",
        },
    )
    frame = result["frame_refs"][0]
    artifact_id = await ctx.create_media_artifact(
        "frame-0001",
        "frame",
        uri=frame["uri"],
        media_metadata=MediaMetadata(
            kind="frame",
            mime_type="image/jpeg",
            frame_index=frame["frame_index"],
            timestamp_start_seconds=frame["timestamp_start_seconds"],
        ),
        lineage=ArtifactLineage(source_blob_refs=["s3://media/demo/input.mp4"], tool_call_ids=["video.extract_frames"]),
    )
    ctx.write_state_patch("frame_artifact", artifact_id)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        register_media_tool_conventions(rt.registry, {"video.extract_frames": fake_extract_frames})
        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(media_tool_agent, run_id=run_id, agent_role="MediaAgent")
        evidence = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
        print(
            json.dumps(
                {
                    "ok": ok,
                    "run_id": run_id,
                    "state": rt.store.final_state(run_id),
                    "tool_ledger": evidence["tool_ledger"],
                    "media_artifacts": evidence["media_artifacts"],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
