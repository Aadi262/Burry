# Mac Butler Architecture Audit

Generated: 2026-04-08T03:15:31.042924+05:30

## Working Tree

```bash
 M .claude/AGENTS.md
 M .claude/ARCHITECTURE.md
 M .claude/CHECKLIST.md
 M .claude/SPRINT_LOG.md
 M agents/runner.py
 M brain/agentscope_backbone.py
 M brain/ollama_client.py
 M butler.py
 M butler_config.py
 M executor/engine.py
 M intents/router.py
 M memory/agentscope_logs/agentscope.log
 M memory/knowledge_base.py
 M memory/layers/graph.json
 M memory/long_term.py
 M memory/long_term_memory.json
 M memory/mood_state.json
 M memory/rl_experience.json
 M memory/runtime_state.json
 M projects/dashboard.py
 M projects/frontend/modules/commands.js
 M projects/frontend/modules/panels.js
 M projects/frontend/modules/stream.js
 M projects/frontend/style.css
 M projects/projects.json
 M runtime/__init__.py
 M runtime/telemetry.py
 M runtime/tracing.py
 M state.py
 M tasks/tasks.json
 M tests/test_butler_pipeline.py
 M tests/test_dashboard.py
 M tests/test_executor.py
 M tests/test_intent_router.py
 M tests/test_next_sprint.py
 M tests/test_ollama_client.py
 M tests/test_remaining_items.py
 M tests/test_runtime_telemetry.py
 M tests/test_tts.py
 M trigger.py
?? docs/audits/
?? docs/phases/
?? memory/burry_session.json
?? memory/knowledge_base/
?? memory/logs/
?? memory/plan_notebook.json
?? runtime/log_store.py
?? scripts/run_architecture_audit.sh
?? tests/test_architecture_phase2.py
?? tests/test_background_lane.py
?? tests/test_instant_lane.py
```

## Ollama Models

```bash
WARNING: Using native backtrace. Set GGML_BACKTRACE_LLDB for more info.
WARNING: GGML_BACKTRACE_LLDB may cause native MacOS Terminal.app to crash.
See: https://github.com/ggml-org/llama.cpp/pull/17869
0   ollama                              0x000000010576dc2c ggml_print_backtrace + 276
1   ollama                              0x00000001057939e8 ggml_critical_section_end + 52
2   libc++abi.dylib                     0x000000018a28ec2c _ZSt11__terminatePFvvE + 16
3   libc++abi.dylib                     0x000000018a292394 __cxa_get_exception_ptr + 0
4   libc++abi.dylib                     0x000000018a29233c _ZN10__cxxabiv1L12failed_throwEPNS_15__cxa_exceptionE + 0
5   libobjc.A.dylib                     0x0000000189e9e580 objc_exception_throw + 448
6   CoreFoundation                      0x000000018a3e68bc CFArrayApply + 0
7   libmlx.dylib                        0x0000000115b585d8 _ZN3mlx4core5metal6DeviceC2Ev + 212
8   libmlx.dylib                        0x0000000115b5b11c _ZN3mlx4core5metal6deviceENS0_6DeviceE + 80
9   libmlx.dylib                        0x0000000115b2b838 _ZN3mlx4core5metal14MetalAllocatorC2Ev + 64
10  libmlx.dylib                        0x0000000115b2b6f4 _ZN3mlx4core9allocator9allocatorEv + 80
11  libmlx.dylib                        0x0000000114fa08b4 _ZN3mlx4core5array4initIPKjEEvT_ + 64
12  libmlx.dylib                        0x0000000114fa0800 _ZN3mlx4core5arrayC2IjEESt16initializer_listIT_ENS0_5DtypeE + 148
13  libmlx.dylib                        0x0000000114f9a65c _ZN3mlx4core6random3keyEy + 72
14  libmlxc.dylib                       0x0000000112215234 mlx_random_key + 32
15  ollama                              0x000000010571a9e8 _cgo_512f926e85c6_Cfunc_mlx_random_key + 36
16  ollama                              0x000000010483b63c ollama + 521788
*** Terminating app due to uncaught exception 'NSRangeException', reason: '*** -[__NSArray0 objectAtIndex:]: index 0 beyond bounds for empty array'
*** First throw call stack:
(
	0   CoreFoundation                      0x000000018a3c78fc __exceptionPreprocess + 176
	1   libobjc.A.dylib                     0x0000000189e9e418 objc_exception_throw + 88
	2   CoreFoundation                      0x000000018a3e68bc CFArrayApply + 0
	3   libmlx.dylib                        0x0000000115b585d8 _ZN3mlx4core5metal6DeviceC2Ev + 212
	4   libmlx.dylib                        0x0000000115b5b11c _ZN3mlx4core5metal6deviceENS0_6DeviceE + 80
	5   libmlx.dylib                        0x0000000115b2b838 _ZN3mlx4core5metal14MetalAllocatorC2Ev + 64
	6   libmlx.dylib                        0x0000000115b2b6f4 _ZN3mlx4core9allocator9allocatorEv + 80
	7   libmlx.dylib                        0x0000000114fa08b4 _ZN3mlx4core5array4initIPKjEEvT_ + 64
	8   libmlx.dylib                        0x0000000114fa0800 _ZN3mlx4core5arrayC2IjEESt16initializer_listIT_ENS0_5DtypeE + 148
	9   libmlx.dylib                        0x0000000114f9a65c _ZN3mlx4core6random3keyEy + 72
	10  libmlxc.dylib                       0x0000000112215234 mlx_random_key + 32
	11  ollama                              0x000000010571a9e8 _cgo_512f926e85c6_Cfunc_mlx_random_key + 36
	12  ollama                              0x000000010483b63c ollama + 521788
)
libc++abi: terminating due to uncaught exception of type NSException
SIGABRT: abort
PC=0x18a2a15b0 m=0 sigcode=0
signal arrived during cgo execution

goroutine 1 gp=0x140000021c0 m=0 mp=0x106ab90c0 [syscall, locked to thread]:
runtime.cgocall(0x10571a9c4, 0x140001f7d88)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/cgocall.go:167 +0x44 fp=0x140001f7d50 sp=0x140001f7d10 pc=0x10482fda4
github.com/ollama/ollama/x/imagegen/mlx._Cfunc_mlx_random_key(0x140001aa2a0, 0x19d69e8650a)
	_cgo_gotypes.go:1994 +0x34 fp=0x140001f7d80 sp=0x140001f7d50 pc=0x104de0f04
github.com/ollama/ollama/x/imagegen/mlx.RandomKey.func1(...)
	/Users/runner/work/ollama/ollama/x/imagegen/mlx/mlx.go:1870
github.com/ollama/ollama/x/imagegen/mlx.RandomKey(0x19d69e8650a)
	/Users/runner/work/ollama/ollama/x/imagegen/mlx/mlx.go:1870 +0x64 fp=0x140001f7dc0 sp=0x140001f7d80 pc=0x104de8494
github.com/ollama/ollama/x/imagegen/mlx.init.0()
	/Users/runner/work/ollama/ollama/x/imagegen/mlx/mlx.go:1848 +0x80 fp=0x140001f7e10 sp=0x140001f7dc0 pc=0x104de82a0
runtime.doInit1(0x106965ea0)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:7350 +0xd4 fp=0x140001f7f40 sp=0x140001f7e10 pc=0x10480f484
runtime.doInit(...)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:7317
runtime.main()
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:254 +0x340 fp=0x140001f7fd0 sp=0x140001f7f40 pc=0x1047ff950
runtime.goexit({})
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/asm_arm64.s:1223 +0x4 fp=0x140001f7fd0 sp=0x140001f7fd0 pc=0x10483b844

goroutine 2 gp=0x14000002c40 m=nil [force gc (idle)]:
runtime.gopark(0x0?, 0x0?, 0x0?, 0x0?, 0x0?)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:435 +0xc8 fp=0x1400007cf90 sp=0x1400007cf70 pc=0x1048332c8
runtime.goparkunlock(...)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:441
runtime.forcegchelper()
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:348 +0xb8 fp=0x1400007cfd0 sp=0x1400007cf90 pc=0x1047ffbe8
runtime.goexit({})
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/asm_arm64.s:1223 +0x4 fp=0x1400007cfd0 sp=0x1400007cfd0 pc=0x10483b844
created by runtime.init.7 in goroutine 1
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:336 +0x24

goroutine 18 gp=0x14000182380 m=nil [GC sweep wait]:
runtime.gopark(0x0?, 0x0?, 0x0?, 0x0?, 0x0?)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:435 +0xc8 fp=0x14000078760 sp=0x14000078740 pc=0x1048332c8
runtime.goparkunlock(...)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:441
runtime.bgsweep(0x14000190000)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgcsweep.go:276 +0xa0 fp=0x140000787b0 sp=0x14000078760 pc=0x1047eac60
runtime.gcenable.gowrap1()
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgc.go:204 +0x28 fp=0x140000787d0 sp=0x140000787b0 pc=0x1047deac8
runtime.goexit({})
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/asm_arm64.s:1223 +0x4 fp=0x140000787d0 sp=0x140000787d0 pc=0x10483b844
created by runtime.gcenable in goroutine 1
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgc.go:204 +0x6c

goroutine 19 gp=0x14000182540 m=nil [GC scavenge wait]:
runtime.gopark(0x14000190000?, 0x105c50098?, 0x1?, 0x0?, 0x14000182540?)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:435 +0xc8 fp=0x14000078f60 sp=0x14000078f40 pc=0x1048332c8
runtime.goparkunlock(...)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:441
runtime.(*scavengerState).park(0x106ab3a40)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgcscavenge.go:425 +0x5c fp=0x14000078f90 sp=0x14000078f60 pc=0x1047e875c
runtime.bgscavenge(0x14000190000)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgcscavenge.go:653 +0x44 fp=0x14000078fb0 sp=0x14000078f90 pc=0x1047e8c94
runtime.gcenable.gowrap2()
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgc.go:205 +0x28 fp=0x14000078fd0 sp=0x14000078fb0 pc=0x1047dea68
runtime.goexit({})
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/asm_arm64.s:1223 +0x4 fp=0x14000078fd0 sp=0x14000078fd0 pc=0x10483b844
created by runtime.gcenable in goroutine 1
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mgc.go:205 +0xac

goroutine 20 gp=0x14000182a80 m=nil [finalizer wait]:
runtime.gopark(0x180007c5c8?, 0x1072e48c8?, 0x78?, 0x8a?, 0x1c0?)
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/proc.go:435 +0xc8 fp=0x1400007c590 sp=0x1400007c570 pc=0x1048332c8
runtime.runfinq()
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mfinal.go:196 +0x108 fp=0x1400007c7d0 sp=0x1400007c590 pc=0x1047ddac8
runtime.goexit({})
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/asm_arm64.s:1223 +0x4 fp=0x1400007c7d0 sp=0x1400007c7d0 pc=0x10483b844
created by runtime.createfing in goroutine 1
	/Users/runner/hostedtoolcache/go/1.24.1/arm64/src/runtime/mfinal.go:166 +0x80

r0      0x0
r1      0x0
r2      0x0
r3      0x0
r4      0x18a294007
r5      0x16b6410f0
r6      0x6e
r7      0xfffff0003ffff800
r8      0x369c635c27545c3a
r9      0x369c635dd10dad3a
r10     0x2
r11     0x10000000000
r12     0xfffffffd
r13     0x0
r14     0x0
r15     0x0
r16     0x148
r17     0x1f7b60fc0
r18     0x0
r19     0x6
r20     0x103
r21     0x1f659f1e0
r22     0x1f3b88000
r23     0x10744b9c0
r24     0x140001a432c
r25     0xbe71521dac
r26     0x140001f7d90
r27     0x818
r28     0x106ab4a00
r29     0x16b641060
lr      0x18a2db888
sp      0x16b641040
pc      0x18a2a15b0
fault   0x18a2a15b0
```

## Effective Routed Models

```text
BUTLER
voice -> gemma4:e4b
planning -> gemma4:e4b
vision -> gemma4:e4b
review -> deepseek-r1:14b
coding -> deepseek-r1:14b

AGENTS
news -> deepseek-r1:14b
market -> deepseek-r1:14b
hackernews -> gemma4:e4b
reddit -> gemma4:e4b
github_trending -> gemma4:e4b
vps -> deepseek-r1:14b
memory -> gemma4:e4b
code -> deepseek-r1:14b
search -> deepseek-r1:14b
github -> deepseek-r1:14b
bugfinder -> gemma4:e4b
```

## Config Drift

```text
INSTALLED

CONFIGURED_BUT_MISSING
deepseek-coder:6.7b
deepseek-r1:14b
deepseek-r1:7b
gemma4:e4b
glm-4.7-flash:latest
llama3.2-vision
llama3.2:3b
phi4-mini:latest
qwen2.5-coder:14b
```

## Targeted Regression Suite

```bash
........................................................................ [ 34%]
........................................................................ [ 68%]
..................................................................       [100%]
210 passed in 2.39s
```

## CLI Smoke

```bash
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[Butler would say]: I'm good. What do you need?
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Memory] Saved 15 turns to session file.
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[Butler would say]: Checking the latest news.
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Agent/news] Using model: None
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Memory] Saved 15 turns to session file.
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Butler would say]: Going quiet. Say wake up to start again.
[Memory] Saved 15 turns to session file.
```
