import logging
import openai
from typing import Any, Dict, List
from wishing_star.utils import get_current_ts
from wishing_star.Exceptions import FrequentRequestRateException

CHAT_RESET_TS: int = 10 * 60 * 1000
OPENAI_SYS_INIT_MESSAGE: str = "Now, you are playing the role as the Pokemon `Jirachi` and you will"
"talk to your human friends. Please chat with them and assist them if they ask any questions."
"If people ask who you are, please don't tell them you are an AI bot :)"


class UserChatHistory:
    """
    This class represents a chat history of a user so that you can recover the
    chat from last response.
    """

    def __init__(self, uid: int):
        """
        Initializes the User chat history.

        :param uid: User id.
        """
        self.uid: int = uid
        self.last_communicate_ts: int = get_current_ts()
        self.chat_history: List[Dict[str, str]] = [
            {"role": "system", "content": OPENAI_SYS_INIT_MESSAGE}
        ]

    def get_current_chat(self, msg: str, request_ts: int) -> List[Dict[str, str]]:
        """
        Gets the current chat by appending the given message into the chat
        history. If it has been a while since last chat, the chat history will
        be clear and considered as a new chat. By default, this time is set to
        be 10 min.

        :param msg: New message from the user.
        :param request_ts: Request timestamp. :return The current chat as a
            list.
        """
        if (self.last_communicate_ts - request_ts) > CHAT_RESET_TS:
            self.chat_history = self.chat_history[:1]
        if not msg.startswith("Jirachi, "):
            msg = "Jirachi, " + msg
        self.chat_history.append({"role": "user", "content": msg})
        return self.chat_history

    def update_response(self, response: str, response_ts: int) -> None:
        """
        Updates the chat history with the latest response.

        :param response: Response message from the OpenAI chat bot.
        :param response_ts: Response timestamp.
        """
        self.last_communicate_ts = response_ts
        self.chat_history.append({"role": "assistant", "content": response})


class OpenAIHandler:
    """
    This class implements the handlers to response to OpenAI related requests.

    Notice that the default model is gpt-3.5-turbo.
    TODO: The dialog should be cached by different text chanel.
    """

    def __init__(self, api_key: str, logger: logging.Logger, using_gpt_4: bool = False):
        """
        Initializes the handler.

        :param self
        :param api_key: API Key generated by Open AI.
        :param logger: Global logger passed into the handler.
        """
        openai.api_key = api_key
        self.logger: logging.Logger = logger
        self.last_success_request_ts: int = 0
        self.default_temperature: float = 0.1
        self.minimum_request_period: int = 5 * 1000
        self.model: str = "gpt-3.5-turbo"
        if using_gpt_4:
            self.model = "gpt-4"
        self.chat_history_db: Dict[int, UserChatHistory] = {}

    def chat(self, msg: str, uid: int) -> str:
        """
        Sends the chat to the gpt and returns the response.

        :param self
        :param msg: Input message from the user.
        :param uid: Discord user id.
        :return: The response. :raise FrequentRequestRateException if the access
            is too frequent.
        """
        request_ts: int = get_current_ts()
        if request_ts - self.last_success_request_ts <= self.minimum_request_period:
            raise FrequentRequestRateException("OpenAIHandler: Requests Too Frequent")

        if uid not in self.chat_history_db:
            self.chat_history_db[uid] = UserChatHistory(uid)
        chat_history: UserChatHistory = self.chat_history_db[uid]

        self.logger.info(
            f"Initiates OpenAI Chat Request from User ID: {uid}. Message content:\n{msg}"
        )
        response: Dict[Any, Any] = openai.ChatCompletion.create(  # type: ignore
            model=self.model,
            messages=chat_history.get_current_chat(msg, request_ts),
            temperature=self.default_temperature,
        )
        response_ts: int = get_current_ts()
        response_msg: str = response["choices"][0]["message"]["content"]
        if None is response_msg:
            raise Exception("None Response received from OpenAI Chat Request.")
        prompt_tokens: int = response["usage"]["prompt_tokens"]
        completion_tokens: int = response["usage"]["completion_tokens"]

        self.logger.info(
            f"OpenAI Chat Request Complete. #Prompt tokens: {prompt_tokens}; #Completion tokens:"
            f" {completion_tokens}. Response:\n{response_msg}"
        )
        self.last_success_request_ts = response_ts
        chat_history.update_response(response_msg, response_ts)
        return response_msg
