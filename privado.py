"""Criptografa os dados da aba Treinos.

Uso:
    SENHA_PRIVADO=... python privado.py caminho/para/treinos.json

Os treinos ficam no repositório privado andryll/cblow-privado; o repositório deste site
é público, então só a versão criptografada (site/treinos.json) é publicada, e ela nem
vai para o git. AES-256-GCM com chave derivada da senha por PBKDF2-SHA256: a página
decifra no navegador com a Web Crypto, sem mandar a senha para lugar nenhum.

Formato de treinos.json (campos numéricos podem ser null quando a print não mostra):
    {"jogos": [{"data": "AAAA-MM-DD", "adversario": "Time", "vitoria": true, "duracao": "28:15",
                "jogadores": [{"nome": "KarlinRox", "campeao": "Sion", "rota": "top",
                               "abates": 1, "mortes": 2, "assistencias": 3, "cs": 150, "dano": 12000}]}]}
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import coletar

ARQ_SITE_TREINOS = coletar.RAIZ / "site" / "treinos.json"
ITERACOES = 600_000  # recomendação da OWASP para PBKDF2-SHA256
CAMPOS_JOGADOR = ["nome", "campeao", "abates", "mortes", "assistencias"]


def b64(dados):
    return base64.b64encode(dados).decode("ascii")


def segundos(duracao):
    """'28:15' -> 1695; aceita também um número de segundos ou null."""
    if duracao in (None, ""):
        return None
    if isinstance(duracao, (int, float)):
        return int(duracao)
    minutos, _, seg = str(duracao).partition(":")
    return int(minutos) * 60 + int(seg or 0)


def validar(treinos):
    """Confere o mínimo de cada jogo, para um erro de digitação não quebrar a página."""
    for i, jogo in enumerate(treinos["jogos"], 1):
        for campo in ("data", "vitoria", "jogadores"):
            if campo not in jogo:
                sys.exit(f"[treinos] jogo {i}: falta o campo {campo!r}")
        jogo["duracao"] = segundos(jogo.get("duracao"))
        for j in jogo["jogadores"]:
            faltando = [c for c in CAMPOS_JOGADOR if c not in j]
            if faltando:
                sys.exit(f"[treinos] jogo {i} ({jogo['data']}), {j.get('nome', '?')}: faltam {faltando}")
    return treinos


def criptografar(dados, senha):
    sal, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITERACOES).derive(senha.encode("utf-8"))
    # O AESGCM devolve o texto cifrado com a tag de 16 bytes no fim, o formato que a Web Crypto espera.
    cifrado = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False).encode("utf-8"), None)
    return {"versao": 1, "kdf": "PBKDF2-SHA256", "iteracoes": ITERACOES, "sal": b64(sal), "iv": b64(iv), "dados": b64(cifrado)}


def main():
    senha = os.environ.get("SENHA_PRIVADO", "")
    if not senha:
        sys.exit("Defina a variável de ambiente SENHA_PRIVADO.")
    if len(sys.argv) < 2:
        sys.exit("Uso: python privado.py caminho/para/treinos.json")
    treinos = validar(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    treinos["gerado_em"] = datetime.now(coletar.BRASILIA).isoformat(timespec="minutes")
    ARQ_SITE_TREINOS.write_text(json.dumps(criptografar(treinos, senha)), encoding="utf-8")
    print(f"[treinos] {len(treinos['jogos'])} jogos de treino criptografados em {ARQ_SITE_TREINOS.name}")


if __name__ == "__main__":
    main()
