import os
import asyncio
import json
import time
import aiohttp
from datetime import datetime
from pytz import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest, TimedOut, Forbidden
from flask import Flask, request, abort

BOT_TOKEN = os.environ.get("BOT_TOKEN", "7695089803:AAG5TlChCJ92qC4omVReqJK24LLvzjdEr4o")

CANAL_FREE = "@craftworld_free"

PIX_CHAVE = "03666009077"
PIX_NOME = "RENER DORNELLES VASCONCELLOS"

TOKENS = {
    "DYNO":        "0x7dc167e270d5ef683ceaf4afcdf2efbdd667a9a7",
    "EARTH":       "0xC89384CD2970C916DC75DA8E11524EBE6D77FA07",
    "COPPER":      "0x64AC88024E1BCC49E3EE145C165914F58998EC9B",
    "STEEL":       "0x798239FEE069E2B5B3C58978AEA92A3D0E16950C",
    "SCREWS":      "0xCC34D8E6A6F61358219D8E8A967ED7F191638449",
    "CERAMICS":    "0x581E54C7A521519E98D256D39852E4C214CAD697",
    "ACID":        "0xCD0C9F170E395CA1ADC16AE9AE8107D50273E2E8",
    "PLASTICS":    "0x8EABB6A3A05AF9FB514482A677B12008A2ED6422",
    "ENERGY":      "0xA3F0F293AEE7CE8B4A3807BF9CC07942DA4E51E8",
    "HYDROGEN":    "0xB7D11863D0D9C39764F981A95AB8AF0AED714C48",
    "DYNAMITE":    "0x2918938CFDE254CC76B68A4F6992927EE779104A",
    "SUSHI":       "0xC146e831C137bbB2e1aF91C30844D224F4778017",
    "LOBSTER":     "0x869DC8b8553788Fa007BB12Ddd31442650559602",
    "DYNODESSERT": "0x4F0585509AaBFc9EA3146ec18F8E6d2e289F288c",
    "WATER":       "0x57A8EB80D6813AEEEB9C8E770011C016F980D581",
    "SASHIMI":     "0x6431221054B04AEFdf94b8Bc1529172ff9860d2c",
    "FIRE":        "0x0E8Edc6f5CaC5dCaE036Ad77Fc0dE4E72404e2Fb",
}

ICONES = {
    "DYNO":        "🦕",
    "EARTH":       "🌍",
    "COPPER":      "🟠",
    "STEEL":       "⚙️",
    "SCREWS":      "🔩",
    "CERAMICS":    "🪔",
    "ACID":        "🧪",
    "PLASTICS":    "🧴",
    "ENERGY":       "⚡",
    "HYDROGEN":    "🧨",
    "DYNAMITE":    "💣",
    "SUSHI":       "🍣",
    "LOBSTER":     "🦞",
    "DYNODESSERT": "🍰",
    "WATER":       "💧",
    "SASHIMI":     "🍱",
    "FIRE":        "🔥",
}

DYNO_ADDR = TOKENS["DYNO"]

ultimos_sinais = []
subscriptions = {}
application = None
SUBS_FILE = "subscriptions.json"

precos_anteriores = {}
dados_diarios = {}
last_day = None
TZ_BRASIL = timezone('America/Sao_Paulo')

last_activity = {}
alertas_enviados_hoje = 0
last_alert_day = None

session = None

def load_subscriptions():
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, 'r') as f:
                data = json.load(f)
                for user_id in data:
                    data[user_id]["tokens"] = set(data[user_id]["tokens"])
                    if "thresholds" not in data[user_id]:
                        data[user_id]["thresholds"] = {}
                    if "targets" not in data[user_id]:
                        data[user_id]["targets"] = {}
                    for token in data[user_id]["tokens"]:
                        if token not in data[user_id]["targets"]:
                            data[user_id]["targets"][token] = {"above": None, "below": None, "triggered_above": False, "triggered_below": False}
                return data
        except Exception as e:
            print(f"Erro ao carregar subscriptions: {e}")
    return {}

def save_subscriptions():
    try:
        data_to_save = {}
        for user_id, info in subscriptions.items():
            data_to_save[user_id] = {
                "tokens": list(info["tokens"]),
                "thresholds": info["thresholds"],
                "targets": info.get("targets", {})
            }
        with open(SUBS_FILE, 'w') as f:
            json.dump(data_to_save, f)
    except Exception as e:
        print(f"Erro ao salvar subscriptions: {e}")

def get_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 PREÇOS ATUAIS", callback_data="precos")],
        [InlineKeyboardButton("📈 ÚLTIMOS SINAIS", callback_data="sinais"),
         InlineKeyboardButton("🔔 MEUS ALERTAS", callback_data="meus_alertas")],
        [InlineKeyboardButton("🔔 ADICIONAR ALERTAS", callback_data="alertas")],
        [InlineKeyboardButton("📈 TOP 10 VOLÁTEIS/LUCRATIVOS DIÁRIO", callback_data="top_diario")],
        [InlineKeyboardButton("📊 ESTATÍSTICAS DO BOT", callback_data="stats_bot")],
        [InlineKeyboardButton("📖 GUIA DE USO", callback_data="guia")],
        [InlineKeyboardButton("❤️ APOIE O BOT", callback_data="apoie")],
    ])

def get_voltar_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ VOLTAR AO MENU", callback_data="menu")]])

def get_meus_alertas_keyboard(user_id):
    data = subscriptions.get(user_id, {"tokens": set(), "thresholds": {}, "targets": {}})
    user_tokens = data["tokens"]
    
    if not user_tokens:
        texto = "🔔 *MEUS ALERTAS*\n\nVocê ainda não configurou nenhum alerta.\nVá em 'ADICIONAR ALERTAS' para começar!"
        return texto, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ VOLTAR AO MENU", callback_data="menu")]])
    
    texto = "🔔 *MEUS ALERTAS*\n\nAlertas ativos:\n"
    keyboard = []
    
    for token in user_tokens:
        icone = ICONES.get(token, "❓")
        thresh = data["thresholds"].get(token, 100.0)
        targets = data["targets"].get(token, {"above": None, "below": None})
        
        linha_principal = f"{icone} {token} ({thresh}%)"
        keyboard.append([
            InlineKeyboardButton(linha_principal, callback_data="dummy"),
            InlineKeyboardButton("Editar", callback_data=f"edit_{token}")
        ])
        
        if targets["above"] or targets["below"]:
            alvos = []
            if targets["above"]: alvos.append(f"↗️{targets['above']}")
            if targets["below"]: alvos.append(f"↘️{targets['below']}")
            linha_alvos = f"     Alvos: {' '.join(alvos)} COIN"
            keyboard.append([InlineKeyboardButton(linha_alvos, callback_data="dummy")])
        
        keyboard.append([InlineKeyboardButton("❌ Excluir", callback_data=f"delete_{token}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ VOLTAR AO MENU", callback_data="menu")])
    return texto, InlineKeyboardMarkup(keyboard)

def get_edit_keyboard(token):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("0.1%", callback_data=f"setperc_{token}_0.1"), InlineKeyboardButton("0.2%", callback_data=f"setperc_{token}_0.2")],
        [InlineKeyboardButton("0.5%", callback_data=f"setperc_{token}_0.5"), InlineKeyboardButton("1%", callback_data=f"setperc_{token}_1")],
        [InlineKeyboardButton("3%", callback_data=f"setperc_{token}_3"), InlineKeyboardButton("5%", callback_data=f"setperc_{token}_5")],
        [InlineKeyboardButton("🔢 % PERSONALIZADO", callback_data=f"custom_perc_{token}")],
        [InlineKeyboardButton("🎯 CONFIGURAR PREÇO ALVO", callback_data=f"target_menu_{token}")],
        [InlineKeyboardButton("⬅️ VOLTAR", callback_data="meus_alertas")]
    ])

def get_target_menu_keyboard(token):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↗️ QUANDO SUBIR ATÉ X COIN", callback_data=f"target_above_{token}")],
        [InlineKeyboardButton("↘️ QUANDO CAIR ATÉ Y COIN", callback_data=f"target_below_{token}")],
        [InlineKeyboardButton("❌ REMOVER ALVOS", callback_data=f"target_remove_{token}")],
        [InlineKeyboardButton("⬅️ VOLTAR", callback_data="meus_alertas")]
    ])

async def get_price_and_volume(session, addr):
    url = f"https://api.geckoterminal.com/api/v2/networks/ronin/tokens/{addr}"
    for _ in range(3):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 429:
                    await asyncio.sleep(10)
                    continue
                response.raise_for_status()
                data = await response.json()
                attributes = data["data"]["attributes"]
                return float(attributes["price_usd"]), float(attributes.get("volume_usd_h24", 0))
        except Exception as e:
            print(f"Erro API {addr}: {e}")
            await asyncio.sleep(2)
    return None, None

async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global subscriptions
    subscriptions = load_subscriptions()
    user_id = str(update.effective_user.id)
    if user_id not in precos_anteriores:
        precos_anteriores[user_id] = {}
    
    welcome = (
        "🎮 *BEM-VINDO AO CFW ALERTAS!* 🎮\n\n"
        "Monitoramento completo dos recursos do Craft World + Fishing Frenzy na Ronin.\n\n"
        "🚀 Alertas por % de variação\n"
        "🎯 Alertas por preço alvo em COIN\n"
        "📊 Preços em tempo real\n"
        "🔄 Botão SWAP direto no Katana\n\n"
        "Tudo 100% gratuito!\n\n"
        "Escolha uma opção:"
    )
    await update.message.reply_text(welcome, parse_mode='Markdown', reply_markup=get_menu_keyboard())

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e):
            pass
        else:
            raise

    user_id = str(update.effective_user.id)
    
    last_activity[user_id] = time.time()
    
    if user_id not in subscriptions:
        subscriptions[user_id] = {"tokens": set(), "thresholds": {}, "targets": {}}
        save_subscriptions()
    if user_id not in precos_anteriores:
        precos_anteriores[user_id] = {}

    data = query.data

    if data == "limpar_alerta":
        try:
            await query.message.delete()
            await query.answer("Alerta limpo! ✅")
        except Exception as e:
            print(f"Erro ao limpar alerta: {e}")
            await query.answer("Não consegui limpar (mensagem antiga?)")
        return

    if data == "menu":
        await safe_edit(query, "🎮 *CFW ALERTAS*\n\nEscolha uma opção:", reply_markup=get_menu_keyboard())

    elif data == "precos":
        msg = "📊 *PREÇOS EM TEMPO REAL*\n\n"
        dyno_result = await get_price_and_volume(session, DYNO_ADDR)
        dyno_usd, _ = dyno_result if dyno_result else (None, None)
        if dyno_usd:
            for nome in TOKENS:
                icone = ICONES.get(nome, "❓")
                result = await get_price_and_volume(session, TOKENS[nome])
                price_usd, _ = result if result else (None, None)
                if price_usd:
                    coin_price = price_usd / dyno_usd if nome != "DYNO" and dyno_usd > 0 else None
                    coin_text = f" (~{coin_price:.4f} COIN)" if coin_price else ""
                    msg += f"{icone} {nome} → ${price_usd:.8f}{coin_text}\n"
                else:
                    msg += f"{icone} {nome} → erro temporário\n"
        msg += "\n🕐 Atualizado agora"
        await safe_edit(query, msg, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

    elif data == "sinais":
        texto = "📈 *ÚLTIMOS 5 SINAIS FREE*\n\n" + "\n".join(ultimos_sinais[-5:]) if ultimos_sinais else "📈 Nenhum sinal ainda... mercado calmo!"
        await safe_edit(query, texto, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

    elif data == "meus_alertas":
        texto, kb = get_meus_alertas_keyboard(user_id)
        await safe_edit(query, texto, reply_markup=kb, parse_mode='Markdown')

    elif data == "alertas":
        kb = []
        for token in TOKENS:
            if token == "DYNO": continue
            icone = ICONES.get(token, "❓")
            ativo = "✅" if token in subscriptions[user_id]["tokens"] else ""
            thresh = subscriptions[user_id]["thresholds"].get(token, 100.0)
            kb.append([InlineKeyboardButton(f"{icone} {token} ({thresh}%) {ativo}", callback_data=f"toggle_{token}")])
        kb.append([InlineKeyboardButton("⬅️ VOLTAR", callback_data="menu")])
        await safe_edit(query, "🔔 *ADICIONAR/REMOVER ALERTAS*\n\nToque para ativar/desativar:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith("toggle_"):
        token = data.split("_")[1]
        if token in subscriptions[user_id]["tokens"]:
            subscriptions[user_id]["tokens"].remove(token)
            subscriptions[user_id]["thresholds"].pop(token, None)
            subscriptions[user_id]["targets"].pop(token, None)
            precos_anteriores[user_id].pop(token, None)
        else:
            subscriptions[user_id]["tokens"].add(token)
            subscriptions[user_id]["thresholds"][token] = 100.0
            subscriptions[user_id]["targets"][token] = {"above": None, "below": None, "triggered_above": False, "triggered_below": False}
        save_subscriptions()
        kb = []
        for t in TOKENS:
            if t == "DYNO": continue
            icone = ICONES.get(t, "❓")
            ativo = "✅" if t in subscriptions[user_id]["tokens"] else ""
            thresh = subscriptions[user_id]["thresholds"].get(t, 100.0)
            kb.append([InlineKeyboardButton(f"{icone} {t} ({thresh}%) {ativo}", callback_data=f"toggle_{t}")])
        kb.append([InlineKeyboardButton("⬅️ VOLTAR", callback_data="menu")])
        await safe_edit(query, "🔔 *ADICIONAR/REMOVER ALERTAS*\n\nToque para ativar/desativar:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith("edit_"):
        token = data.split("_")[1]
        await safe_edit(query, f"⚙️ *EDITAR ALERTA - {token}*\n\nEscolha:", reply_markup=get_edit_keyboard(token), parse_mode='Markdown')

    elif data.startswith("setperc_"):
        token = data.split("_")[1]
        perc = float(data.split("_")[2])
        subscriptions[user_id]["thresholds"][token] = perc
        save_subscriptions()
        texto, kb = get_meus_alertas_keyboard(user_id)
        await safe_edit(query, texto + f"\n✅ Variação de {token} alterada para {perc}%!", reply_markup=kb, parse_mode='Markdown')

    elif data.startswith("custom_perc_"):
        token = data.split("_")[2]
        context.user_data["custom_perc_token"] = token
        context.user_data["awaiting_perc"] = True
        await query.message.reply_text(f"🔢 Digite o novo % mínimo para {token} (ex: 2.5):", reply_markup=ForceReply())

    elif data.startswith("target_menu_"):
        token = data.split("_")[2]
        await safe_edit(query, f"🎯 *PREÇO ALVO - {token}*\n\nConfigure:", reply_markup=get_target_menu_keyboard(token), parse_mode='Markdown')

    elif data.startswith("target_above_"):
        token = data.split("_")[2]
        context.user_data["target_token"] = token
        context.user_data["target_direction"] = "above"
        context.user_data["awaiting_target"] = True
        await query.message.reply_text("↗️ Digite o preço em COIN para alerta QUANDO SUBIR ATÉ lá (ex: 27):", reply_markup=ForceReply())

    elif data.startswith("target_below_"):
        token = data.split("_")[2]
        context.user_data["target_token"] = token
        context.user_data["target_direction"] = "below"
        context.user_data["awaiting_target"] = True
        await query.message.reply_text("↘️ Digite o preço em COIN para alerta QUANDO CAIR ATÉ lá (ex: 22):", reply_markup=ForceReply())

    elif data.startswith("target_remove_"):
        token = data.split("_")[2]
        if token in subscriptions[user_id]["targets"]:
            subscriptions[user_id]["targets"][token] = {"above": None, "below": None, "triggered_above": False, "triggered_below": False}
            save_subscriptions()
        texto, kb = get_meus_alertas_keyboard(user_id)
        await safe_edit(query, texto + f"\n❌ Alvos de preço de {token} removidos!", reply_markup=kb, parse_mode='Markdown')

    elif data.startswith("delete_"):
        token = data.split("_")[1]
        subscriptions[user_id]["tokens"].discard(token)
        subscriptions[user_id]["thresholds"].pop(token, None)
        subscriptions[user_id]["targets"].pop(token, None)
        precos_anteriores[user_id].pop(token, None)
        save_subscriptions()
        texto, kb = get_meus_alertas_keyboard(user_id)
        await safe_edit(query, texto, reply_markup=kb, parse_mode='Markdown')

    elif data == "top_diario":
        msg = "📈 *TOP 10 VOLÁTEIS/LUCRATIVOS DIÁRIO*\n\n"
        now = datetime.now(TZ_BRASIL)
        msg += f"Atualizado até {now.strftime('%H:%M')} (reseta às 00:00 Brasília)\n\n"

        volatil = []
        for token in TOKENS:
            if token == "DYNO": continue
            if token in dados_diarios:
                d = dados_diarios[token]
                if d['initial'] > 0:
                    faixa = (d['high'] - d['low']) / d['initial'] * 100
                    volatil.append((token, faixa))
        volatil.sort(key=lambda x: x[1], reverse=True)
        msg += "🌀 *Top Voláteis (% faixa diária)*:\n"
        for i, (t, v) in enumerate(volatil[:10], 1):
            msg += f"{i}º {ICONES.get(t, '❓')} {t} {v:.2f}%\n"

        lucrativo = []
        for token in TOKENS:
            if token == "DYNO": continue
            if token in dados_diarios:
                d = dados_diarios[token]
                if d['initial'] > 0:
                    ganho = (d['current'] - d['initial']) / d['initial'] * 100
                    lucrativo.append((token, ganho))
        lucrativo.sort(key=lambda x: x[1], reverse=True)
        msg += "\n💰 *Top Lucrativos (% ganho diário)*:\n"
        for i, (t, g) in enumerate(lucrativo[:10], 1):
            msg += f"{i}º {ICONES.get(t, '❓')} {t} {g:+.2f}%\n"

        await safe_edit(query, msg, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

    elif data == "stats_bot":
        total_users = len(subscriptions)
        now = time.time()
        
        ativos_5min = sum(1 for t in last_activity.values() if now - t < 300)
        ativos_1h = sum(1 for t in last_activity.values() if now - t < 3600)
        ativos_24h = sum(1 for t in last_activity.values() if now - t < 86400)
        
        texto = (
            f"📊 *ESTATÍSTICAS DO BOT*\n\n"
            f"👥 Total cadastrados: *{total_users}*\n\n"
            f"🕒 Ativos últimas 24h: {ativos_24h}\n"
            f"🕒 Ativos última 1h: {ativos_1h}\n"
            f"🕒 Ativos últimos 5min: {ativos_5min}\n\n"
            f"⚡ Alertas enviados hoje: {alertas_enviados_hoje}"
        )
        await safe_edit(query, texto, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

    elif data == "guia":
        guia = (
            "📖 *GUIA DE USO*\n\n"
            "1. 'ADICIONAR ALERTAS' → toque nos recursos\n"
            "2. 'Editar' → mude o % ou defina preço alvo em COIN\n"
            "3. Receba alertas privados com preço anterior/atual e botão SWAP\n\n"
            "Tudo automático e gratuito! 🚀"
        )
        await safe_edit(query, guia, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

    elif data == "apoie":
        apoio = (
            "❤️ *APOIE O BOT*\n\n"
            f"Pix: `{PIX_CHAVE}`\n"
            f"Nome: {PIX_NOME}\n\n"
            "Ajuda a manter o bot 24h online! Obrigado 🙏"
        )
        await safe_edit(query, apoio, reply_markup=get_voltar_keyboard(), parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    last_activity[user_id] = time.time()

    text = update.message.text.strip().replace("%", "")

    if context.user_data.get("awaiting_perc"):
        token = context.user_data.pop("custom_perc_token", None)
        try:
            val = float(text)
            if not (0.05 <= val <= 50):
                await update.message.reply_text("Use um valor entre 0.05% e 50%!")
                return
            subscriptions[user_id]["thresholds"][token] = val
            save_subscriptions()
            await update.message.reply_text(f"✅ % mínimo de {token} alterado para {val}%!", reply_markup=get_menu_keyboard())
        except:
            await update.message.reply_text("Digite um número válido! Ex: 2.5")
        finally:
            context.user_data.pop("awaiting_perc", None)

    elif context.user_data.get("awaiting_target"):
        token = context.user_data.pop("target_token", None)
        direction = context.user_data.pop("target_direction", None)
        try:
            price = float(text)
            if price <= 0:
                await update.message.reply_text("O preço deve ser positivo!")
                return
            if token not in subscriptions[user_id]["targets"]:
                subscriptions[user_id]["targets"][token] = {"above": None, "below": None, "triggered_above": False, "triggered_below": False}
            subscriptions[user_id]["targets"][token][direction] = price
            subscriptions[user_id]["targets"][token][f"triggered_{direction}"] = False
            save_subscriptions()
            dir_text = "subir até" if direction == "above" else "cair até"
            await update.message.reply_text(f"✅ Alerta configurado! Aviso quando {token} {dir_text} {price} COIN", reply_markup=get_menu_keyboard())
        except:
            await update.message.reply_text("Digite um número válido! Ex: 27.5")
        finally:
            context.user_data.pop("awaiting_target", None)

async def enviar_sinal(token, variacao):
    icone = ICONES.get(token, "❓")
    direcao = "🚀" if variacao > 0 else "📉"
    cor = "🟢" if variacao > 0 else "🔴"
    swap_url = f"https://katana.roninchain.com/swap?inputCurrency={DYNO_ADDR}&outputCurrency={TOKENS[token]}"
    texto = f"{direcao} *SINAL CRAFT WORLD* {direcao}\n\n{cor} *{token}* {variacao:+.2f}%\n\nAgora no Ronin!"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 SWAP NO KATANA", url=swap_url)]])
    ultimos_sinais.append(f"{icone} {token} {variacao:+.2f}%")
    if len(ultimos_sinais) > 20:
        ultimos_sinais.pop(0)
    try:
        await application.bot.send_message(CANAL_FREE, texto, parse_mode='Markdown', reply_markup=kb)
    except Exception as e:
        print(f"Erro enviando sinal: {e}")

async def enviar_alerta_preco(uid, token, preco_atual, alvo, direcao):
    icone = ICONES.get(token, "❓")
    swap_url = f"https://katana.roninchain.com/swap?inputCurrency={DYNO_ADDR}&outputCurrency={TOKENS[token]}"
    texto = f"🎯 *PREÇO ALVO ATINGIDO!* 🎯\n\n{icone} *{token}* {direcao} {alvo} COIN\n💰 Preço atual: {preco_atual:.4f} COIN 🚨"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 SWAP NO KATANA AGORA", url=swap_url)],
        [InlineKeyboardButton("❌ Limpar Alerta", callback_data="limpar_alerta")],
        [InlineKeyboardButton("⬅️ MENU", callback_data="menu")]
    ])
    try:
        await application.bot.send_message(int(uid), texto, parse_mode='Markdown', reply_markup=kb)
    except Forbidden:
        print(f"Usuário {uid} bloqueou o bot - ignorando alerta")
    except Exception as e:
        print(f"Erro enviando alerta preço pra {uid}: {e}")

async def monitorar_precos(app):
    global application, session, subscriptions, last_day, dados_diarios, alertas_enviados_hoje, last_alert_day
    application = app
    
    session = aiohttp.ClientSession()
    
    subscriptions = load_subscriptions()
    
    precos_antigos_global = {}
    
    last_day = datetime.now(TZ_BRASIL).day
    last_alert_day = last_day
    
    while True:
        now = datetime.now(TZ_BRASIL)
        current_day = now.day
        
        if current_day != last_day:
            dados_diarios.clear()
            last_day = current_day
            print("Novo dia - reset dados diários")
        
        if current_day != last_alert_day:
            alertas_enviados_hoje = 0
            last_alert_day = current_day

        dyno_result = await get_price_and_volume(session, DYNO_ADDR)
        dyno_usd, _ = dyno_result if dyno_result else (None, None)
        if not dyno_usd or dyno_usd <= 0:
            await asyncio.sleep(40)
            continue

        tasks = [get_price_and_volume(session, addr) for addr in TOKENS.values() if addr != DYNO_ADDR]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        token_list = [nome for nome in TOKENS if nome != "DYNO"]
        for nome, result in zip(token_list, results):
            if isinstance(result, Exception):
                print(f"Erro ao buscar {nome}: {result}")
                continue
            preco_usd, _ = result
            if not preco_usd: continue
            preco_coin = preco_usd / dyno_usd

            if nome not in dados_diarios:
                dados_diarios[nome] = {'initial': preco_coin, 'high': preco_coin, 'low': preco_coin, 'current': preco_coin}
            else:
                d = dados_diarios[nome]
                d['high'] = max(d['high'], preco_coin)
                d['low'] = min(d['low'], preco_coin)
                d['current'] = preco_coin

            if nome in precos_antigos_global:
                var = (preco_coin - precos_antigos_global[nome]) / precos_antigos_global[nome] * 100

                for uid, data in list(subscriptions.items()):
                    if nome in data["tokens"]:
                        thresh = data["thresholds"].get(nome, 100.0)
                        if abs(var) >= thresh:
                            if uid not in precos_anteriores:
                                precos_anteriores[uid] = {}
                            preco_anterior = precos_anteriores[uid].get(nome, precos_antigos_global[nome])
                            direcao_emoji = "🚀" if var > 0 else "📉"
                            cor = "🟢" if var > 0 else "🔴"
                            diferenca = preco_coin - preco_anterior

                            swap_url = f"https://katana.roninchain.com/swap?inputCurrency={DYNO_ADDR}&outputCurrency={TOKENS[nome]}"
                            kb = InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 SWAP NO KATANA AGORA", url=swap_url)],
                                [InlineKeyboardButton("❌ Limpar Alerta", callback_data="limpar_alerta")],
                                [InlineKeyboardButton("⬅️ VOLTAR AO MENU", callback_data="menu")]
                            ])

                            texto = (
                                f"{direcao_emoji} *ALERTA PESSOAL - {nome}* {direcao_emoji}\n\n"
                                f"{ICONES.get(nome, '❓')} *Recurso:* {nome}\n"
                                f"{cor} *Variação:* {var:+.2f}%\n\n"
                                f"📉 Preço anterior: {preco_anterior:.4f} COIN\n"
                                f"📈 Preço atual:     {preco_coin:.4f} COIN\n"
                                f"💥 Diferença:       {diferenca:+.4f} COIN"
                            )

                            try:
                                await application.bot.send_message(int(uid), texto, parse_mode='Markdown', reply_markup=kb)
                                precos_anteriores[uid][nome] = preco_coin
                                alertas_enviados_hoje += 1
                            except Forbidden:
                                print(f"Usuário {uid} bloqueou o bot - removendo da lista")
                                del subscriptions[uid]
                                save_subscriptions()
                            except Exception as e:
                                print(f"Erro enviando alerta pra {uid}: {e}")

                if abs(var) >= 4.0:
                    await enviar_sinal(nome, var)

            for uid, data in list(subscriptions.items()):
                if nome in data["tokens"] and nome in data["targets"]:
                    t = data["targets"][nome]
                    if t["above"] and not t["triggered_above"] and preco_coin >= t["above"]:
                        await enviar_alerta_preco(uid, nome, preco_coin, t["above"], "subiu para")
                        subscriptions[uid]["targets"][nome]["triggered_above"] = True
                        save_subscriptions()
                    if t["below"] and not t["triggered_below"] and preco_coin <= t["below"]:
                        await enviar_alerta_preco(uid, nome, preco_coin, t["below"], "caiu para")
                        subscriptions[uid]["targets"][nome]["triggered_below"] = True
                        save_subscriptions()

            precos_antigos_global[nome] = preco_coin

        await asyncio.sleep(40)

    await session.close()

async def post_init(app: Application):
    asyncio.create_task(monitorar_precos(app))

# ================== FLASK SETUP FOR RENDER ==================
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    return "Bot is alive! 🚀", 200

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data(as_text=True)
        update = Update.de_json(json.loads(json_string), application.bot)
        asyncio.run(application.process_update(update))
        return '', 200
    abort(403)

@flask_app.before_first_request
def set_webhook():
    asyncio.run(application.bot.set_webhook(url=f"https://bot-telegram-y409.onrender.com/webhook"))

if __name__ == "__main__":
    subscriptions = load_subscriptions()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("BOT CFW ALERTAS - RODANDO COM WEBHOOK NO RENDER!")
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
