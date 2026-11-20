"""
Interactive Command-Line Interface for System Kernel.
Provides an interactive developer REPL to run coding tasks,
inspect centralized workspace state, manage open files,
simulate rate limits, and observe transparent failovers with zero context drift.
"""

import sys
import os
import json
from pathlib import Path
import colorama
from colorama import Fore, Back, Style

from kernel.engine import SystemKernel
from kernel.types import ModelConfig
from kernel.test_verifier import TestVerifier


def print_banner():
    colorama.init(autoreset=True)
    print(Fore.CYAN + Style.BRIGHT + "=" * 70)
    print(Fore.CYAN + Style.BRIGHT + "   SYSTEM KERNEL // MULTI-MODEL DEVELOPER ENVIRONMENT")
    print(Fore.WHITE + "   Single Source of Truth  *  Dynamic Model Agnosticism  *  Zero Drift")
    print(Fore.CYAN + Style.BRIGHT + "=" * 70)
    print(Fore.YELLOW + "Type a coding task prompt or use slash commands:")
    print(Fore.WHITE + "  /status             - Inspect workspace snapshot and active models")
    print(Fore.WHITE + "  /open <file>        - Open file into state buffer and set active")
    print(Fore.WHITE + "  /files              - List files in workspace and open buffers")
    print(Fore.WHITE + "  /models             - View registered models and fallback chain")
    print(Fore.WHITE + "  /set-model <name>   - Switch primary model")
    print(Fore.WHITE + "  /simulate-429       - Toggle simulated HTTP 429 rate limit on primary")
    print(Fore.WHITE + "  /verify             - Run automated project unit tests")
    print(Fore.WHITE + "  /diff               - View unified diff of last applied mutation")
    print(Fore.WHITE + "  /undo               - Rollback last state mutation")
    print(Fore.WHITE + "  /snapshot           - Display centralized state snapshot JSON")
    print(Fore.WHITE + "  /exit               - Quit REPL")
    print(Fore.CYAN + "-" * 70)


def run_cli(project_root: str = "."):
    colorama.init(autoreset=True)
    kernel = SystemKernel(project_root=project_root)
    print_banner()

    # Pre-open any files if they exist
    existing_files = kernel.state_manager.list_project_files()
    if existing_files:
        first_file = existing_files[0]
        try:
            kernel.state_manager.open_file(first_file, set_as_active=True)
            print(Fore.GREEN + f"[+] Automatically opened initial active file: {first_file}")
        except Exception:
            pass

    while True:
        try:
            active_file = kernel.state_manager.snapshot.active_file or "None"
            prompt_header = f"\n{Fore.GREEN}[Kernel:{kernel.primary_model} | active:{active_file}]{Fore.WHITE} > "
            user_input = input(prompt_header).strip()

            if not user_input:
                continue

            if user_input in ("/exit", "/quit", "exit", "quit"):
                print(Fore.CYAN + "Shutting down System Kernel. State preserved.")
                break

            elif user_input == "/status":
                snap = kernel.state_manager.snapshot
                print(Fore.MAGENTA + "\n=== WORKSPACE SNAPSHOT STATUS ===")
                print(f"Active File:   {Fore.YELLOW}{snap.active_file}")
                print(f"Open Files:    {Fore.YELLOW}{list(snap.open_files.keys())}")
                print(f"History Turns: {Fore.YELLOW}{len(snap.recent_history)}")
                print(f"Primary Model: {Fore.CYAN}{kernel.primary_model}")
                print(f"Fallback Models: {Fore.CYAN}{[m.name for m in kernel.registry.list_models() if m.is_fallback]}")

            elif user_input.startswith("/open "):
                file_target = user_input[6:].strip()
                try:
                    kernel.state_manager.open_file(file_target, set_as_active=True)
                    print(Fore.GREEN + f"[+] Opened '{file_target}' into buffer and set as active file.")
                except Exception as e:
                    print(Fore.RED + f"[-] Error opening file: {e}")

            elif user_input == "/files":
                open_files = set(kernel.state_manager.snapshot.open_files.keys())
                disk_files = kernel.state_manager.list_project_files()
                print(Fore.MAGENTA + "\n=== PROJECT FILES ===")
                for df in disk_files:
                    marker = f"{Fore.GREEN}[OPEN/BUFFERED]" if df in open_files else f"{Fore.WHITE}[on disk]"
                    active_marker = f"{Fore.YELLOW} <ACTIVE>" if df == kernel.state_manager.snapshot.active_file else ""
                    print(f"  {df} {marker}{active_marker}")

            elif user_input == "/models":
                print(Fore.MAGENTA + "\n=== REGISTERED MODELS ===")
                for m in kernel.registry.list_models():
                    tag = f"{Fore.GREEN}(PRIMARY)" if m.name == kernel.primary_model else (f"{Fore.BLUE}(FALLBACK)" if m.is_fallback else "")
                    sim_tag = f" {Fore.RED}[429 SIMULATED]" if m.simulate_429 else ""
                    print(f"  - {Fore.CYAN}{m.name:<18} {Fore.WHITE}provider: {m.provider:<10} priority: {m.priority} {tag}{sim_tag}")

            elif user_input.startswith("/set-model "):
                new_model = user_input[11:].strip()
                try:
                    kernel.set_primary_model(new_model)
                    print(Fore.GREEN + f"[+] Primary model changed to '{new_model}'")
                except KeyError as e:
                    print(Fore.RED + f"[-] {e}")

            elif user_input == "/simulate-429":
                try:
                    cfg = kernel.registry.get_config(kernel.primary_model)
                    cfg.simulate_429 = not cfg.simulate_429
                    state = f"{Fore.RED}ENABLED (Will trigger 429 Rate Limit)" if cfg.simulate_429 else f"{Fore.GREEN}DISABLED (Normal)"
                    print(Fore.YELLOW + f"[*] Rate Limit Simulation on '{kernel.primary_model}': {state}")
                except Exception as e:
                    print(Fore.RED + f"[-] {e}")

            elif user_input == "/verify":
                print(Fore.BLUE + "[*] Running project unit tests...")
                passed, output = TestVerifier.run_tests(kernel.state_manager.project_root)
                color = Fore.GREEN if passed else Fore.RED
                print(color + output)

            elif user_input == "/diff":
                history = kernel.state_manager.snapshot.recent_history
                found = False
                for turn in reversed(history):
                    if turn.diffs:
                        print(Fore.MAGENTA + f"\n=== LATEST DIFFS (Turn {turn.turn_id}) ===")
                        for d in turn.diffs:
                            print(Fore.CYAN + f"File: {d.get('file')} ({d.get('action')})")
                            diff_lines = (d.get("diff") or "").split("\n")
                            for line in diff_lines:
                                if line.startswith("+") and not line.startswith("+++"):
                                    print(Fore.GREEN + line)
                                elif line.startswith("-") and not line.startswith("---"):
                                    print(Fore.RED + line)
                                else:
                                    print(Fore.WHITE + line)
                        found = True
                        break
                if not found:
                    print(Fore.YELLOW + "[!] No diffs found in recent interaction history.")

            elif user_input == "/undo":
                restored = kernel.state_manager.rollback()
                if restored:
                    print(Fore.GREEN + "[+] Rolled back to previous workspace snapshot and synced to disk.")
                else:
                    print(Fore.YELLOW + "[!] Undo stack empty.")

            elif user_input == "/snapshot":
                snap_dict = kernel.state_manager.snapshot.model_dump()
                print(Fore.CYAN + json.dumps(snap_dict, indent=2))

            else:
                # Execute coding prompt through System Kernel
                print(Fore.BLUE + f"[*] Executing task through System Kernel via primary model '{kernel.primary_model}'...")
                res = kernel.execute(task_prompt=user_input)

                # Report Failover & Handoff
                if res.handoff_notes:
                    print(Fore.YELLOW + Style.BRIGHT + "\n[!] TRANSPARENT FAILOVER OCCURRED:")
                    for note in res.handoff_notes:
                        print(Fore.YELLOW + f"    {note}")

                print(Fore.CYAN + f"\n[Model Used: {res.model_used} | Latency: {res.latency_seconds}s | Status: {res.status}]")
                print(Fore.WHITE + Style.BRIGHT + "\nResponse:")
                print(res.response_text)

                # Report state mutations
                if res.mutations_applied:
                    print(Fore.GREEN + Style.BRIGHT + "\nMutations Automatically Applied to State & Disk:")
                    for m in res.mutations_applied:
                        status_str = f"{Fore.GREEN}OK" if m.success else f"{Fore.RED}FAILED ({m.error})"
                        print(f"  - [{m.action.upper()}] {m.file_path}: {status_str}")
                        if m.diff:
                            print(Fore.LIGHTBLACK_EX + m.diff)

        except KeyboardInterrupt:
            print("\n" + Fore.CYAN + "Exiting System Kernel.")
            break
        except Exception as e:
            print(Fore.RED + f"\n[-] Unexpected REPL error: {e}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_cli(root)
