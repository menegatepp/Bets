import sys
from colorama import init, Fore, Style

init(autoreset=True)

from display import (
    print_header,
    print_arb_opportunity,
    print_no_arbs,
    print_odds_table,
    prompt_bankroll,
    prompt_manual_odds,
)
from arb_engine import scan_for_arbs

session = {
    "bankroll": 500.0,
    "odds_lines": [],
}


def menu():
    print(Fore.CYAN + "\n" + "─" * 40)
    print("  [1] Buscar odds do HLTV agora")
    print("  [2] Inserir odds manualmente")
    print("  [3] Definir bankroll")
    print("  [4] Escanear arbitragem")
    print("  [5] Ver todas as odds carregadas")
    print("  [0] Sair")
    print("─" * 40 + Style.RESET_ALL)
    return input("  Opção: ").strip()


def action_fetch_hltv():
    print(Fore.YELLOW + "\nAbrindo HLTV... aguarde (pode levar 15-30s)." + Style.RESET_ALL)
    try:
        from hltv_scraper import scrape_hltv_odds
        lines = scrape_hltv_odds()
        if lines:
            session["odds_lines"].extend(lines)
            print(Fore.GREEN + f"{len(lines)} linha(s) de odds carregada(s) do HLTV." + Style.RESET_ALL)
            print_odds_table(lines)
        else:
            print(Fore.YELLOW + "Nenhuma odd foi encontrada na página do HLTV." + Style.RESET_ALL)
            print("Isso pode ocorrer se o HLTV mudou o layout ou não há partidas agora.")
            print("Use a opção [2] para inserir odds manualmente.")
    except Exception as e:
        print(Fore.RED + f"Erro ao buscar do HLTV: {e}" + Style.RESET_ALL)
        print("Use a opção [2] para inserir odds manualmente.")


def action_manual_input():
    new_lines = prompt_manual_odds()
    if new_lines:
        session["odds_lines"].extend(new_lines)


def action_set_bankroll():
    session["bankroll"] = prompt_bankroll(session["bankroll"])
    print(Fore.GREEN + f"Bankroll definido: R${session['bankroll']:.2f}" + Style.RESET_ALL)


def action_scan():
    if not session["odds_lines"]:
        print(Fore.YELLOW + "Nenhuma odd carregada. Use [1] ou [2] primeiro." + Style.RESET_ALL)
        return
    print(Fore.CYAN + f"\nEscaneando {len(session['odds_lines'])} linha(s) com bankroll R${session['bankroll']:.2f}..." + Style.RESET_ALL)
    opps = scan_for_arbs(session["odds_lines"], session["bankroll"])
    if opps:
        print(Fore.GREEN + f"\n{len(opps)} oportunidade(s) encontrada(s):\n" + Style.RESET_ALL)
        for arb in opps:
            print_arb_opportunity(arb)
    else:
        print_no_arbs()


def action_show_odds():
    print_odds_table(session["odds_lines"])


def main():
    print_header()
    print(f"  Bankroll inicial: R${session['bankroll']:.2f}")

    while True:
        choice = menu()
        if choice == "1":
            action_fetch_hltv()
        elif choice == "2":
            action_manual_input()
        elif choice == "3":
            action_set_bankroll()
        elif choice == "4":
            action_scan()
        elif choice == "5":
            action_show_odds()
        elif choice == "0":
            print(Fore.CYAN + "Saindo. Bons lucros!" + Style.RESET_ALL)
            sys.exit(0)
        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()
