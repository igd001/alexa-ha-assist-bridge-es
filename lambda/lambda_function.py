# -*- coding: utf-8 -*-
# Pont Alexa <-> Home Assistant Assist (conversation.process) + chuchotement optionnel
import logging, json, urllib.request
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_model import Intent, Slot
from ask_sdk_model.dialog import ElicitSlotDirective


HA_URL   = "https://YOUR_HA_URL.ui.nabu.casa"  # your Home Assistant URL (Nabu Casa remote or your own HTTPS)
HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"  # HA profile -> Security -> Long-lived access tokens
HA_LANG  = "es-ES"
HA_AGENT = "conversation.google_ai_conversation"
QUESTION_ENTITY = "input_text.assist_alexa_question"
TIMEOUT = 4

logger = logging.getLogger(__name__); logger.setLevel(logging.INFO)

def _wrap(text, whisper):
    if whisper:
        return '<amazon:effect name="whispered">' + text + '</amazon:effect>'
    return text

def _req(path, data=None, method="GET"):
    req = urllib.request.Request(HA_URL + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Authorization": "Bearer " + HA_TOKEN, "Content-Type": "application/json"},
        method=method)
    return json.load(urllib.request.urlopen(req, timeout=TIMEOUT))

def ha_converse(text, session_attributes=None):
    try:
        payload = {"text": text, "language": HA_LANG}
        if HA_AGENT:
            payload["agent_id"] = HA_AGENT

        if session_attributes:
            conversation_id = session_attributes.get("conversation_id")
            if conversation_id:
                payload["conversation_id"] = conversation_id

        r = _req("/api/conversation/process", payload, "POST")

        new_conversation_id = r.get("conversation_id")
        if session_attributes is not None and new_conversation_id:
            session_attributes["conversation_id"] = new_conversation_id

        return r["response"]["speech"]["plain"]["speech"] or "Hecho."
    except Exception as e:
        logger.exception(e)
        return "Lo siento, no he podido contactar con la Gemini."

def _reelicit_command(response_builder, speech):
    return (
        response_builder
        .speak(speech)
        .add_directive(
            ElicitSlotDirective(
                slot_to_elicit="command",
                updated_intent=Intent(
                    name="CommandIntent",
                    confirmation_status="NONE",
                    slots={
                        "command": Slot(
                            name="command",
                            confirmation_status="NONE"
                        )
                    }
                )
            )
        )
        .response
    )


def ha_get_question():
    try:
        r = _req("/api/states/" + QUESTION_ENTITY)
        val = r.get("state", "")
        if val and val not in ("unknown", "unavailable"):
            return json.loads(val)
    except Exception as e:
        logger.exception(e)
    return None

class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes
        sa["conversation_id"] = None
        sa["esperando_comando"] = True

        return _reelicit_command(
            handler_input.response_builder,
            "Sí, dime."
        )
        
class YesHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes
        sa["esperando_comando"] = True
        respuesta = ha_converse("sí", sa)

        return _reelicit_command(
            handler_input.response_builder,
            respuesta
        )

class NoHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes
        sa["esperando_comando"] = True
        respuesta = ha_converse("no", sa)

        return _reelicit_command(
            handler_input.response_builder,
            respuesta
        )

class ModeChatHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ModeChatIntent")(handler_input)
    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes
        ans = ha_converse("active le mode chat")
        return handler_input.response_builder.speak(_wrap(ans, sa.get("whisper"))).response

class CommandHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("CommandIntent")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes
        sa["esperando_comando"] = True
        cmd = ask_utils.request_util.get_slot_value(
            handler_input=handler_input,
            slot_name="command"
        ) or ""

        if cmd.strip().lower() in {"adiós", "adios", "ya está", "ya esta"}:
            sa["esperando_comando"] = False
            sa["conversation_id"] = None
            return handler_input.response_builder.speak("Hasta luego.").response
        respuesta = ha_converse(cmd, sa)

        return _reelicit_command(
            handler_input.response_builder,
            respuesta
        )
        
class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        s = "Dites une commande, par exemple : la poubelle est sortie."
        return handler_input.response_builder.speak(s).ask(s).response

class StopHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes

        if sa.get("esperando_comando"):
            return (
                handler_input.response_builder
                .speak("Sigo aquí. Dime el comando.")
                .add_directive(
                    ElicitSlotDirective(
                        slot_to_elicit="command",
                        updated_intent=Intent(
                            name="CommandIntent",
                            confirmation_status="NONE",
                            slots={
                                "command": Slot(
                                    name="command",
                                    confirmation_status="NONE"
                                )
                            }
                        )
                    )
                )
                .response
            )

        return handler_input.response_builder.speak("Hasta luego.").response

class CancelHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input)

    def handle(self, handler_input):
        sa = handler_input.attributes_manager.session_attributes

        if sa.get("esperando_comando"):
            return (
                handler_input.response_builder
                .speak("Vale. Dime qué quieres hacer.")
                .add_directive(
                    ElicitSlotDirective(
                        slot_to_elicit="command",
                        updated_intent=Intent(
                            name="CommandIntent",
                            confirmation_status="NONE",
                            slots={
                                "command": Slot(
                                    name="command",
                                    confirmation_status="NONE"
                                )
                            }
                        )
                    )
                )
                .response
            )

        return handler_input.response_builder.speak("Hasta luego.").response

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
        s = "Je n'ai pas compris, repetez ?"
        return handler_input.response_builder.speak(s).ask(s).response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)
    def handle(self, handler_input):
        return handler_input.response_builder.response

class CatchAll(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception): return True
    def handle(self, handler_input, exception):
        logger.exception(exception)
        return handler_input.response_builder.speak("Il y a eu un souci.").response

sb = SkillBuilder()
for h in [LaunchHandler(), YesHandler(), NoHandler(), ModeChatHandler(), CommandHandler(),
          HelpHandler(), StopHandler(), CancelHandler(), FallbackHandler(), SessionEndedHandler()]:
    sb.add_request_handler(h)
sb.add_exception_handler(CatchAll())
lambda_handler = sb.lambda_handler()
