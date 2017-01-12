from telegram.ext import Updater, CommandHandler, InlineQueryHandler, MessageHandler, Filters
from telegram import InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto, InlineQueryResult, TelegramError
from src.LatexConverter import LatexConverter
from src.PreambleManager import PreambleManager
from src.ResourceManager import ResourceManager
import logging 
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Process, Lock

class InLaTeXbot():
    
    def __init__(self, updater, devnullChatId=-1):

        self._updater = updater
        self._latexConverter = LatexConverter()
        self._preambleManager = PreambleManager()
        self._resourceManager = ResourceManager()
        self._devnullChatId = devnullChatId

        self._updater.dispatcher.add_handler(CommandHandler('start', self.onStart))
        self._updater.dispatcher.add_handler(CommandHandler('abort', self.onAbort))
        self._updater.dispatcher.add_handler(CommandHandler("help", self.onHelp))
        self._updater.dispatcher.add_handler(CommandHandler('registercustompreamble', self.onRegisterCustomPreamble))
        self._updater.dispatcher.add_handler(CommandHandler('getmypreamble', self.onGetMyPreamble))
        self._updater.dispatcher.add_handler(CommandHandler('getdefaultpreamble', self.onGetDefaultPreamble))
        

        inline_caps_handler = InlineQueryHandler(self.onInlineQuery)
        self._updater.dispatcher.add_handler(inline_caps_handler)
        
        self._messageHandler = None
        
        self._logger = logging.getLogger('inlatexbot')
        self._logger.setLevel("DEBUG")
        loggingHandler = TimedRotatingFileHandler('log/inlatexbot.log', when="midnight", backupCount=1)
        loggingHandler.setFormatter(logging.Formatter(fmt='%(asctime)s.%(msecs)03d %(message)s', datefmt='%I:%M:%S'))
        self._logger.addHandler(loggingHandler)
        
        self._locks = {}
        
    
    def launch(self):
        self._updater.start_polling()
        
    def stop(self):
        self._updater.stop()
    
    def onStart(self, bot, update):
        update.message.reply_text(self._resourceManager.getString("greeting_line_one"))
        with open("resources/demo.png", "rb") as f: 
            self._updater.bot.sendPhoto(update.message.from_user.id, f)
        update.message.reply_text(self._resourceManager.getString("greeting_line_two"))

    def onAbort(self, bot, update):
        if self._messageHandler is None:
            update.message.reply_text(self._resourceManager.getString("nothing_to_abort"))
        else:
            self._updater.dispatcher.remove_handler(self._messageHandler, 1)
            self._messageHandler = None
            update.message.reply_text(self._resourceManager.getString("operation_aborted"))
    
    def onHelp(self, bot, update):
        with open("resources/available_commands.html", "r") as f:
            update.message.reply_text(f.read(), parse_mode="HTML")
    
    def onGetMyPreamble(self, bot, update):
        try:
            preamble = self._preambleManager.getPreambleFromDatabase(update.message.from_user.id)
            update.message.reply_text(self._resourceManager.getString("your_preamble_custom")+preamble)
        except KeyError:
            preamble = self._preambleManager.getPreambleFromDatabase("default")
            update.message.reply_text(self._resourceManager.getString("your_preamble_default")+preamble)
            
    def onGetDefaultPreamble(self, bot, update):
        preamble = self._preambleManager.getPreambleFromDatabase("default")
        update.message.reply_text(self._resourceManager.getString("default_preamble")+preamble)
    
    def onRegisterCustomPreamble(self, bot, update):
        self._messageHandler = MessageHandler(Filters.text, self.onPreambleArrived)
        self._updater.dispatcher.add_handler(self._messageHandler, 1)
        update.message.reply_text(self._resourceManager.getString("register_preamble"))
    
    def onPreambleArrived(self, bot, update):
        preamble = update.message.text
        update.message.reply_text(self._resourceManager.getString("checking_preamble"))
        if self._preambleManager.validatePreamble(preamble):
            self._preambleManager.putPreambleToDatabase(update.message.from_user.id, preamble)
            update.message.reply_text(self._resourceManager.getString("preamble_registered"))
            self._updater.dispatcher.remove_handler(self._messageHandler, 1)
            self._messageHandler = None
        else:
            update.message.reply_text(self._resourceManager.getString("preamble_invalid"))
        
    def onInlineQuery(self, bot, update):
        query = update.inline_query.query
        senderId = update.inline_query.from_user.id
        if not query:
            return
        self._logger.debug("Received inline query: "+query+", from user: "+str(senderId))
        
        lock = None
        try:
            lock = self._locks[senderId]
        except KeyError:
            lock = self._locks[senderId] = Lock()
        Process(target = self.respondToInlineQueryTask, args=(bot, update.inline_query.id, query, senderId, lock)).start()
        
    def respondToInlineQueryTask(self, bot, query_id, query, senderId, lock):
        lock.acquire()
        self._logger.debug("Acquired lock for %d, query_id: %s", senderId, query_id)
        try:
            expressionPngFileStream = self._latexConverter.convertExpressionToPng(query, senderId)
            latex_picture_id = bot.sendPhoto(self._devnullChatId, expressionPngFileStream).photo[0].file_id
            self._logger.debug("Image successfully uploaded, id: "+latex_picture_id)
            bot.answerInlineQuery(query_id, [InlineQueryResultCachedPhoto(id=0, photo_file_id=latex_picture_id)], cache_time=0)
        except ValueError:
            self._logger.debug("Wrong syntax in the query!")
            bot.answerInlineQuery(query_id, [InlineQueryResultArticle(id=0, title=self._resourceManager.getString("latex_syntax_error"), 
                                                                            input_message_content=InputTextMessageContent(query))], cache_time=0)
        except TelegramError as err:
            self._logger.error(err)
            bot.answerInlineQuery(query_id, [InlineQueryResultArticle(id=0, title=self._resourceManager.getString("telegram_error")+str(err), 
                                                                            input_message_content=InputTextMessageContent(query))], cache_time=0)
        finally:
            self._logger.debug("Releasing lock for %d", senderId)
            lock.release()
            
if __name__ == '__main__':
    bot = InLaTeXbot()
    bot.launch()

