# Requirements: junespark local inference modes

Agent-facing requirements for integrating MechaHarness with the home-network
inference stack on **junespark** (`192.168.1.21`, NVIDIA DGX Spark / GB10).

Status: MechaHarness is not complete yet. Prefer implementing against these
contracts early so agent loops can attach without reworking the host stack.

## Host inventory

| Host | Role | Notes |
|------|------|-------|
| `junespark` `192.168.1.21` | Exclusive GPU inference | One profile at a time (128 GB unified memory) |
| `chappeau` `192.168.1.28` | Filer / registry | Not the primary inference host |

Operator CLI on junespark:

```bash
~/inference/infer list
~/inference/infer load <profile>
~/inference/infer wait <profile>
~/inference/infer validate <profile>
~/inference/infer unload
```

Repo path: `~/dev/home_network/junespark/inference` (also mirrored under
`/home/rlee/home_network/junespark/inference` on the Spark).

## Profiles / modes

Only one profile may be loaded. MechaHarness should treat the active profile as
the current inference backend capability set.

| Profile | Purpose | Endpoint | Served model id | HF weights |
|---------|---------|----------|-----------------|------------|
| `reason-max` | Strongest reasoning on one Spark | `http://192.168.1.21:8000/v1` | `nemotron-3-super` | `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` |
| `reason-fast` | Fast agent / tool-loop workhorse | `http://192.168.1.21:8000/v1` | `nemotron-35-lightning` | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` |
| `reason-local` | Offline fallback (already cached) | `http://192.168.1.21:8000/v1` | `qwen3-30b-thinking` | `Qwen/Qwen3-30B-A3B-Thinking-2507` |
| `media` | Image / video / audio generation | `http://192.168.1.21:8188` | ComfyUI UI + workflow API | Flux.2-dev (gated), `Lightricks/LTX-2.3`, ACE-Step v1.5 via AEON image |

### Selection guidance for agents

- Default complex reasoning / planning → `reason-max`
- Multi-turn tool loops, sub-agents, high QPS local work → `reason-fast`
- No HF access / offline smoke tests → `reason-local`
- Image, synchronized A/V, music generation → `media` (not OpenAI chat)

Do **not** assume `media` and a reason profile can run together. Switching modes
is an explicit host operation (`infer load ...`) and evicts the previous stack.

## Required MechaHarness capabilities

### 1. OpenAI-compatible reasoning backend

- Backend name suggestion: `junespark` or reuse `vllm` with overrideable base URL
- Defaults when reason profile is active:
  - `MECHA_BASE_URL=http://192.168.1.21:8000/v1`
  - `MECHA_API_KEY` can be any non-empty placeholder (local vLLM does not require auth today)
  - `MECHA_MODEL` must match the **served model id** from the table above, not the HF repo id
- Must support:
  - `/v1/models`
  - `/v1/chat/completions`
  - streaming and non-streaming
  - optional `reasoning` / `reasoning_content` fields (thinking models)
  - tool-calling parsers when the loaded profile enables them (`qwen3_coder` on Nemotron profiles)

### 2. Profile awareness

MechaHarness should be able to:

1. Discover which profile is active (CLI probe or small status file / API later)
2. Refuse or warn if the requested capability does not match the loaded profile
   - e.g. ask for image generation while `reason-max` is loaded
3. Optionally request a mode switch (future): call out to host automation rather than
   embedding Docker Compose inside MechaHarness

Suggested status probe until a dedicated API exists:

```bash
ssh rlee@192.168.1.21 '~/inference/infer status'
# or read /home/rlee/home_network/junespark/inference/.active-profile
```

### 3. Local validation contract

Before complex harness runs, MechaHarness (or CI) should call the host validator:

```bash
ssh rlee@192.168.1.21 '~/inference/infer validate'
# or: ~/inference/infer validate reason-fast
```

Validation expectations:

- reason profiles: `/v1/models` lists served id; `/v1/chat/completions` returns non-empty
  assistant text and/or reasoning text
- media profile: HTTP 200/302 from ComfyUI root (`http://192.168.1.21:8188/`)

Exit code `0` means the mode is safe to use.

### 4. Media mode (future agent tools)

Not OpenAI chat. Plan separate tools for:

- submit / poll ComfyUI workflows (Flux.2 stills, LTX-2.3 A/V, ACE-Step audio)
- fetch outputs from `/home/rlee/june_data/comfy/output` (or an HTTP artifact endpoint later)
- long-running jobs (minutes), not interactive token streaming

Gated Hugging Face access is required for Flux.2 (`black-forest-labs/FLUX.2-dev`).
The host stores `HF_TOKEN` in `junespark/inference/.env` (gitignored).

### 5. Cost / events

Local Spark inference still emits token usage from vLLM. Map vLLM `usage` into
MechaHarness `Cost` events with a local pricing profile (can be `$0` unit cost but
still track tokens/time).

## Non-goals for the first integration

- Running MechaHarness agent loops inside the GPU container
- Co-locating reason + media on one Spark
- Multi-Spark tensor parallel (only one Spark today)
- Treating ComfyUI as an OpenAI chat backend

## Acceptance checks

- [ ] `infer validate reason-local` passes against a live Spark
- [ ] `infer validate reason-fast` passes after first weight download
- [ ] `infer validate reason-max` passes after first weight download
- [ ] `infer validate media` passes once ComfyUI is up (Flux gate accepted)
- [ ] MechaHarness can complete a pass-through and a tool-loop run against
      `MECHA_BASE_URL=http://192.168.1.21:8000/v1` with the active served model id
- [ ] MechaHarness fails clearly when media tools are requested while a reason
      profile is loaded

## Operator notes

- First `reason-max` / `reason-fast` load downloads tens of GB into
  `/home/rlee/models/huggingface`
- First `media` load can pull a very large AEON model set; ensure disk headroom
  on the 3.7T Spark NVMe
- Keep swap off / unused for large unified-memory loads when possible
