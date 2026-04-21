from colorama import Fore, Style


MARKET_LABELS = {
    "h2h": "Vencedor da Partida",
    "maps_total": "Total de Mapas (Over/Under)",
    "maps_winner_map1": "Vencedor Mapa 1",
    "maps_winner_map2": "Vencedor Mapa 2",
    "maps_winner_map3": "Vencedor Mapa 3",
}

MARKET_CHOICES = [
    ("h2h", "Vencedor da Partida"),
    ("maps_total", "Total de Mapas (Over/Under)"),
    ("maps_winner_map1", "Vencedor Mapa 1"),
    ("maps_winner_map2", "Vencedor Mapa 2"),
    ("maps_winner_map3", "Vencedor Mapa 3"),
]


def print_header():
    print(Fore.CYAN + "=" * 54)
    print("  CS2 ARBITRAGE SCANNER  |  hltv.org")
    print("=" * 54 + Style.RESET_ALL)


def print_arb_opportunity(arb):
    line = arb.odds_line
    match_label = f"{line.team_home} vs {line.team_away}"
    market_label = MARKET_LABELS.get(line.market, line.market)

    print(Fore.GREEN + "╔" + "═" * 52 + "╗")
    print(f"║  ARB FOUND: {arb.arb_percent:.2f}% lucro garantido" + " " * max(0, 52 - 34 - len(f"{arb.arb_percent:.2f}")) + "║")
    print(f"║  Partida : {match_label:<41}║")
    print(f"║  Mercado : {market_label:<41}║")
    print("╠" + "═" * 52 + "╣")
    print(f"║  {'Time':<14} {'Casa':<12} {'Odds':>5}   {'Stake':>10}   {'Retorno':>10} ║")
    print("║" + "─" * 52 + "║")
    for outcome, stake in arb.stakes:
        ret = round(stake * outcome.odds, 2)
        name = outcome.name[:13]
        book = outcome.bookmaker[:11]
        print(f"║  {name:<14} {book:<12} {outcome.odds:>5.2f}   R${stake:>9.2f}   R${ret:>9.2f} ║")
    print("╠" + "═" * 52 + "╣")
    total_staked = sum(s for _, s in arb.stakes)
    print(f"║  Total apostado : R${total_staked:>9.2f}" + " " * 21 + "║")
    print(f"║  Retorno garantido: R${arb.target_payout:>9.2f}  (lucro: R${arb.guaranteed_profit:.2f})" + " " * max(0, 52 - 47 - len(f"{arb.guaranteed_profit:.2f}")) + "║")
    print("╚" + "═" * 52 + "╝" + Style.RESET_ALL)
    print()


def print_no_arbs():
    print(Fore.YELLOW + "Nenhuma arbitragem encontrada nas odds carregadas.")
    print("Dica: adicione odds de mais casas pelo menu [2]." + Style.RESET_ALL)


def print_odds_table(lines: list):
    if not lines:
        print(Fore.YELLOW + "Nenhuma odd carregada ainda." + Style.RESET_ALL)
        return
    print(Fore.CYAN + f"\n{'Partida':<28} {'Mercado':<28} {'Casa':<12} {'Time':<16} {'Odd':>5}" + Style.RESET_ALL)
    print("─" * 95)
    for line in lines:
        match_label = f"{line.team_home} vs {line.team_away}"
        market_label = MARKET_LABELS.get(line.market, line.market)
        for outcome in line.outcomes:
            print(f"{match_label:<28} {market_label:<28} {outcome.bookmaker:<12} {outcome.name:<16} {outcome.odds:>5.2f}")
    print()


def prompt_bankroll(current: float) -> float:
    while True:
        try:
            val = input(f"Digite seu bankroll em R$ (atual: R${current:.2f}): ").strip()
            if not val:
                return current
            v = float(val.replace(",", "."))
            if v > 0:
                return v
            print("Digite um valor positivo.")
        except ValueError:
            print("Valor inválido. Use números (ex: 500 ou 1000.50).")


def prompt_manual_odds() -> list:
    from models import Outcome, OddsLine

    print(Fore.CYAN + "\n── Inserir odds manualmente ──" + Style.RESET_ALL)
    match_name = input("Nome da partida (ex: 9z vs alka): ").strip()
    if not match_name:
        print("Nome inválido.")
        return []

    parts = [p.strip() for p in match_name.split("vs")]
    home = parts[0] if len(parts) >= 1 else "Time 1"
    away = parts[1] if len(parts) >= 2 else "Time 2"
    match_id = match_name.lower().replace(" ", "_").replace("vs", "v")

    print("\nEscolha o mercado:")
    for i, (key, label) in enumerate(MARKET_CHOICES, 1):
        print(f"  [{i}] {label}")
    while True:
        try:
            choice = int(input("Opção: ").strip())
            if 1 <= choice <= len(MARKET_CHOICES):
                market_key, market_label = MARKET_CHOICES[choice - 1]
                break
        except ValueError:
            pass
        print("Opção inválida.")

    # Para maps_total os desfechos são Over/Under, senão são os times
    if market_key == "maps_total":
        outcome_names = ["Over", "Under"]
    elif market_key == "h2h":
        outcome_names = [home, away]
    else:
        outcome_names = [home, away]

    print(f"\nQuantas casas você tem odds? (mínimo 2): ", end="")
    while True:
        try:
            n_books = int(input().strip())
            if n_books >= 1:
                break
        except ValueError:
            pass
        print("Número inválido, tente novamente: ", end="")

    lines = []
    for i in range(n_books):
        print(f"\n── Casa {i+1} ──")
        bookmaker = input("Nome da casa (ex: 1xBet): ").strip() or f"Casa {i+1}"
        outcomes = []
        for name in outcome_names:
            while True:
                try:
                    raw = input(f"Odd decimal para '{name}': ").strip().replace(",", ".")
                    odd = float(raw)
                    if odd > 1.0:
                        outcomes.append(Outcome(name=name, odds=odd, bookmaker=bookmaker))
                        break
                except ValueError:
                    pass
                print("Odd inválida (ex: 2.10). Tente novamente.")

        lines.append(OddsLine(
            match_id=match_id,
            team_home=home,
            team_away=away,
            market=market_key,
            outcomes=outcomes,
            source="manual",
        ))

    print(Fore.GREEN + f"\n{len(lines)} linha(s) adicionada(s) para '{match_name}'." + Style.RESET_ALL)
    return lines
