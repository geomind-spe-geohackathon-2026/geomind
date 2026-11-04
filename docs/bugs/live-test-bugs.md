# geomind: bugs found by the live test-and-debug loop (2026-11-03)

Counts only problems found by live DeepSeek runs. Model mistakes that need no code change are not counted.

| # | Found in | Bug | Fixed in |
|---|---|---|---|
| 1 | live 1 (0.4.15) | CSV first column "date", no way to rename it to "time" | 0.4.18 (set_case columns=) |
| 2 | live 1 | case without header: error gave no skeleton | 0.4.18 |
| 3 | live 1 | read_stored with a wrong path gave no hint (17 misuses) | 0.4.18 |
| 4 | live 1 | read_document read the same pages again and again (63 calls) | 0.4.18 (already_read) |
| 5 | live 1 | `--loop design` refused attached files without case.json | 0.4.18 |
| 6 | live 1 | provider retry had built-in defaults (against the no-defaults rule) | 0.4.19 |
| 7 | live 2 (0.4.18) | max_tokens not capped by the context window, OpenRouter 400s | 0.4.19 |
| 8 | live 2 | CSV named but files= not passed: no retry hint | 0.4.19 |
| 9 | live 2 | invalid_unit gave no corrected example | 0.4.19 |
| 10 | live 2 | requirements put inside changes: no hint | 0.4.19 |
| 11 | live 2 | build_plant without header: no plant skeleton | 0.4.19 |
| 12 | live 2 | read_stored on a text result returned an empty list | 0.4.19 |
| 13 | live 3 (0.4.19) | invalid_unit rewritten into case_incomplete with a wrong path | 0.4.20 |
| 14 | live 3 | old-shape requirements flooded suggestions with paths | 0.4.20 |
| 15 | live 3 | gemini's per-row errors passed through unsummarised (365 lines) | 0.4.20 |
| 16 | live 3 | read_document force=true repeats not counted | 0.4.20 |
| 17 | live 4 (0.4.20) | CLI ended the run (exit 1) on a free-text answer | 0.4.21 (re-ask, waiting, resume) |
| 18 | live 4 | search_documents did not search attached files (site stayed empty) | 0.4.21 |
| 19 | live 4 | read_stored stored parts again (46 calls) | 0.4.21 |
| 20 | live 5 (0.4.21) | empty searches gave no guidance (147 searches for prices not in the PDF) | dev a4c9776 |
| 21 | live 5 | renamed column called by its old name: no suggestion | dev a4c9776 |
| 22 | live 6 (0.4.22.dev1) | each round started from scratch, no summary of the last round | dev 47603c2 |
| 23 | live 6 | search_documents returned CSV rows as text hits | dev 47603c2 |
| 24 | live 7 (0.4.22.dev2) | CLI cost shown for a run waiting inside a nested run left out the nested run's cost (0.033 shown vs 0.093 real; the cap itself worked) | dev 70b2c43 |
| 25 | live 7 | the round after a failed verification started without the last round's handover (#22 only half fixed) | dev 70b2c43 |
| 26 | live 7 | design loop stopped (repeated_failure) at round 2 of 5 when two rounds recorded no design | dev 70b2c43 |
| 27 | live 7 | designer asked the user on its last allowed step; after the answer no step was left to use it | dev 70b2c43 |
| 28 | live 8 (0.4.22.dev3) | a JSON object sent as a string (changes, plant) got only pydantic's raw error, no hint (3 times) | dev fb27551 |
| 29 | live 9 (0.4.22.dev4) | read_document gave PDF text one word per line, so tables (ground values on page 2) were unreadable and the model asked to guess | dev 5e93a05 |
| 30 | Sahand review (13:14) | reaching max_steps ended the round; max_steps had a built-in default of 30 (no-defaults rule) | dev 44b0b1a |
| 31 | live 9 | model refused to assume equipment values even when the user allowed assumptions (prompt rule clash) | dev efb1066 (Formulator: chooses with reason, user confirms) |
| 32 | Formulator test | read_document page / read_stored part over 2,000 chars kept whole for one step only, then cut to an outline; the brief was re-read 16 times | dev 8d6a30d |
| 33 | Formulator test | assumptions had no fields for reason and source, so recording confirmed values was refused | dev d4c6d74 (additive fields) |
| 34 | Formulator test | read_stored on a stored part larger than the limit (e.g. a schema) returned only an outline; the model re-read it 7 times | dev 81d90a2 |
| 35 | Formulator test (case tree) | the case key tree left out the economics keys, so the model read the economics schema piece by piece (input 416k -> 896k tokens) | dev 1480bd3 (plus partial set_case and a window for kept parts; input 896k -> 539k) |
| 36 | Formulator re-test (dev13) | nothing limited one call's output: one 74-char set_case call generated 103k output tokens ($0.14 of the $0.20 run) | dev 7a0ef62 (required GEOMIND_MAX_OUTPUT_TOKENS; a cut-off answer runs nothing and the model is asked for a shorter one) |
| 37 | Designer test (run 0cea2c80) | when the project already holds a case.json, the Formulator's task didn't say so; it asked the user for the whole case instead of loading it | dev 04e07fc + fdbfed8 (the design loop loads case.json by rule; Formulator fills only what is missing) |
| 38 | Designer test D1 | build_plant named a missing case value (site.air.pressure) but didn't say to ask for a case change; the Designer tried 12 times to put it in the plant | dev d2c8cf6 (+34600fa lint) |
| 39 | Designer test D1 round 2 | a plant class's 110 issues took 30.8k chars, so read_plant shrank to an outline and the Designer read it part by part (read_stored 29 times) | dev 1691873 (compact issues 30.8k -> 21.2k; result kept for the kept turns) |
| 40 | Designer test D2 round 2 | nothing stopped the same failing call repeating: build_plant with an empty plant {} 35 times in a row | dev 4e435bb (stop after max_retries identical failures, with the reason) |
| 41 | Designer test D2 round 2 (root cause of #40; also the QA 'empty plant' on prod) | build_plant's tool schema declared plant as a bare object with no keys, so the model sent {} | dev bed4120 + 48f9439 + fbaae14 (schema names gemini's plant keys; empty plant refused with the smallest valid file as a hint) |

gemini gap found (requested by Sahand, fixed by gemini): CSV times without offset could not be read -> gemini 0.5.13 `time_zone`.

New tool from the loop: `--replay FILE --replay-steps N` (replay recorded steps at no cost, continue live).

## Progress per live run
| Run | Version | Cost | How far |
|---|---|---|---|
| 1 | 0.4.15 | $0.29 | no case |
| 2 | 0.4.18 | $0.04 | no case (400 errors) |
| 3 | 0.4.19 | $0.27 | no case (CSV times) |
| 4 | 0.4.20 | $0.08 | case saved, first plant built |
| 5 | 0.4.21 | $0.27 | case time only |
| 6 | 0.4.22.dev1 | $0.25 | full case in last round |
| 7 | 0.4.22.dev2 (replay 7 steps) | $0.10 | case in round 1, plant built; stopped at round 2 (bugs 25-27) |
| 8 | 0.4.22.dev3 (replay to the question) | $0.21 | site from PDF, case complete, plants hc1/hc2 built; plant values incomplete, no design (30-step limit) |
| F1 | 0.4.22.dev9 Formulator alone | $0.01 | case complete and accepted by gemini (demand, site from PDF, 11 requirements, economics); 8 values confirmed by the user |

| F2 | 0.4.22.dev13 Formulator alone | $0.20 | case set; 36 calls, 17 set_case; one runaway call cost $0.14 (#36) |

| F3 | 0.4.22.dev14 Formulator (replay 8 calls, then live) | $0.07 | case complete (demand, site, 9 requirements, economics, utilities); 37 calls, 14 set_case, 452k in / 38k out |
| D1 | 0.4.22.dev18 Designer on project case (round 1) | $0.03 | first simulate (2); build_plant 18, size_plant 3, describe_module 2 (was 20/4/33, no simulate); Designer asked for a case change, Formulator handled it with one confirmation |
| D1 r2 | 0.4.22.dev18 round 2 | $0.064 | stopped: same pattern (utilities.gas.composition not in PDF, Designer tried it in the plant; #38 already fixed on dev19); read_stored 38, describe_module 18, build_plant 15 |
| D2 | 0.4.22.dev19 replay + live (round 1) | $0.034 | #38 works: build_plant 6 (was 18), size_plant 2; case change asked early, one confirmation |
| D2 r2 | 0.4.22.dev20 round 2 | $0.066 | stopped: Designer asked for gas.composition, then sent build_plant with an empty plant 35 times (#40) |

Loop budget since 12:11 UTC: $1.66 of $5.

New: patch_plant (04ec864) builds a plant step by step, one module's values per patch (plants need 92-136 values).
