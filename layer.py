import datetime
import logging
import os
import sys
from time import *

from yowsup.common import YowConstants

from yowsup.layers import YowLayerEvent
from yowsup.layers.auth import YowAuthenticationProtocolLayer
from yowsup.layers.interface import YowInterfaceLayer, ProtocolEntityCallback
from yowsup.layers.network import YowNetworkLayer
from yowsup.layers.protocol_acks.protocolentities import *
from yowsup.layers.protocol_chatstate.protocolentities import *
from yowsup.layers.protocol_contacts.protocolentities import *
from yowsup.layers.protocol_groups.protocolentities import *
from yowsup.layers.protocol_ib.protocolentities import *
from yowsup.layers.protocol_iq.protocolentities import *
from yowsup.layers.protocol_media.mediauploader import MediaUploader
from yowsup.layers.protocol_media.protocolentities import *
from yowsup.layers.protocol_messages.protocolentities import *
from yowsup.layers.protocol_presence.protocolentities import *
from yowsup.layers.protocol_privacy.protocolentities import *
from yowsup.layers.protocol_profiles.protocolentities import *
from yowsup.layers.protocol_receipts.protocolentities import *

from yowsup.common.tools import Jid
from yowsup.common.optionalmodules import PILOptionalModule, AxolotlOptionalModule

from cli import Cli, clicmd
from bot import Bot


BOT = Bot()


logger = logging.getLogger(__name__)


class YowsupCliLayer(Cli, YowInterfaceLayer):
    PROP_RECEIPT_AUTO = "org.openwhatsapp.yowsup.prop.cli.autoreceipt"
    PROP_RECEIPT_KEEPALIVE = "org.openwhatsapp.yowsup.prop.cli.keepalive"
    PROP_CONTACT_JID = "org.openwhatsapp.yowsup.prop.cli.contact.jid"
    EVENT_LOGIN = "org.openwhatsapp.yowsup.event.cli.login"
    EVENT_START = "org.openwhatsapp.yowsup.event.cli.start"
    EVENT_SENDANDEXIT = "org.openwhatsapp.yowsup.event.cli.sendandexit"

    MESSAGE_FORMAT = "[{FROM}({TIME})]:[{MESSAGE_ID}]\t {MESSAGE}"

    DISCONNECT_ACTION_PROMPT = 0
    DISCONNECT_ACTION_EXIT   = 1

    ACCOUNT_DEL_WARNINGS = 4

    def __init__(self):
        super(YowsupCliLayer, self).__init__()
        YowInterfaceLayer.__init__(self)
        self.accountDelWarnings = 0
        self.connected = False
        self.username = None
        self.sendReceipts = True
        self.disconnectAction = self.__class__.DISCONNECT_ACTION_PROMPT
        self.credentials = None

        self.LASTIQ = ""
        self.MESSAGES = []


        #add aliases to make it user to use commands. for example you can then do:
        # /message send foobar "HI"
        # and then it will get automaticlaly mapped to foobar's jid
        self.jidAliases = {
            # "NAME": "PHONE@s.whatsapp.net"
        }

    def getBot(self):
        return BOT

    def aliasToJid(self, calias):
        for alias, ajid in self.jidAliases.items():
            if calias.lower() == alias.lower():
                return self.normalizeJid(ajid)
        return self.normalizeJid(calias)

    def jidToAlias(self, jid):
        for alias, ajid in self.jidAliases.items():
            if ajid == jid:
                return alias
        return jid

    def normalizeJid(self, number):
        if '@' in number:
            return number
        elif "-" in number:
            return "%s@g.us" % number

        return "%s@s.whatsapp.net" % number

    def setCredentials(self, username, password):
        self.getLayerInterface(YowAuthenticationProtocolLayer).setCredentials(username, password)

    def onEvent(self, layerEvent):
        if layerEvent.getName() == self.__class__.EVENT_START:
            self.startInput()
            return True
        elif layerEvent.getName() == self.__class__.EVENT_SENDANDEXIT:
            credentials = layerEvent.getArg("credentials")
            target = layerEvent.getArg("target")
            message = layerEvent.getArg("message")
            self.sendMessageAndDisconnect(credentials, target, message)
            return True
        elif layerEvent.getName() == YowNetworkLayer.EVENT_STATE_DISCONNECTED:
            self.output("Disconnected: %s" % layerEvent.getArg("reason"))
            if self.disconnectAction == self.__class__.DISCONNECT_ACTION_PROMPT:
                self.connected = False
                self.notifyInputThread()
            else:
                os._exit(os.EX_OK)

    def assertConnected(self):
        if self.connected:
            return True
        else:
            self.output("Not connected", tag = "Error", prompt = False)
            return False

    #### batch cmds #####
    def sendMessageAndDisconnect(self, credentials, jid, message):
        self.disconnectAction = self.__class__.DISCONNECT_ACTION_EXIT
        self.queueCmd("/login %s %s" % credentials)
        self.queueCmd("/message send %s \"%s\" wait" % (jid, message))
        self.queueCmd("/disconnect")
        self.startInput()

    ########## PRESENCE ###############
    @clicmd("Set presence name")
    def presence_name(self, name):
        if self.assertConnected():
            entity = PresenceProtocolEntity(name = name)
            self.toLower(entity)

    @clicmd("Set presence as available")
    def presence_available(self):
        if self.assertConnected():
            entity = AvailablePresenceProtocolEntity()
            self.toLower(entity)

    @clicmd("Set presence as unavailable")
    def presence_unavailable(self):
        if self.assertConnected():
            entity = UnavailablePresenceProtocolEntity()
            self.toLower(entity)

    @clicmd("Unsubscribe from contact's presence updates")
    def presence_unsubscribe(self, contact):
        if self.assertConnected():
            entity = UnsubscribePresenceProtocolEntity(self.aliasToJid(contact))
            self.toLower(entity)

    @clicmd("Subscribe to contact's presence updates")
    def presence_subscribe(self, contact):
        if self.assertConnected():
            entity = SubscribePresenceProtocolEntity(self.aliasToJid(contact))
            self.toLower(entity)

    ########### END PRESENCE #############

    ########### ib #######################
    @clicmd("Send clean dirty")
    def ib_clean(self, dirtyType):
        if self.assertConnected():
            entity = CleanIqProtocolEntity("groups", YowConstants.DOMAIN)
            self.toLower(entity)

    @clicmd("Ping server")
    def ping(self):
        if self.assertConnected():
            entity = PingIqProtocolEntity(to = YowConstants.DOMAIN)
            self.toLower(entity)

    ######################################

    ####### contacts/ profiles ####################
    @clicmd("Set status text")
    def profile_setStatus(self, text):
        if self.assertConnected():
            def onSuccess(resultIqEntity, originalIqEntity):
                self.output("Status updated successfully")

            def onError(errorIqEntity, originalIqEntity):
                logger.error("Error updating status")

            entity = SetStatusIqProtocolEntity(text)
            self._sendIq(entity, onSuccess, onError)

    @clicmd("Get profile picture for contact")
    def contact_picture(self, jid):
        if self.assertConnected():
            entity = GetPictureIqProtocolEntity(self.aliasToJid(jid), preview=False)
            self._sendIq(entity, self.onGetContactPictureResult)

    @clicmd("Get profile picture preview for contact")
    def contact_picturePreview(self, jid):
        if self.assertConnected():
            entity = GetPictureIqProtocolEntity(self.aliasToJid(jid), preview=True)
            self._sendIq(entity, self.onGetContactPictureResult)

    @clicmd("Get lastseen for contact")
    def contact_lastseen(self, jid):
        if self.assertConnected():
            def onSuccess(resultIqEntity, originalIqEntity):
                self.output("%s lastseen %s seconds ago" % (resultIqEntity.getFrom(), resultIqEntity.getSeconds()))

            def onError(errorIqEntity, originalIqEntity):
                logger.error("Error getting lastseen information for %s" % originalIqEntity.getTo())

            entity = LastseenIqProtocolEntity(self.aliasToJid(jid))
            self._sendIq(entity, onSuccess, onError)

    @clicmd("Set profile picture")
    def profile_setPicture(self, path):
        if self.assertConnected():
            with PILOptionalModule(failMessage = "No PIL library installed, try install pillow") as imp:
                Image = imp("Image")
                def onSuccess(resultIqEntity, originalIqEntity):
                    self.output("Profile picture updated successfully")

                def onError(errorIqEntity, originalIqEntity):
                    logger.error("Error updating profile picture")

                #example by @aesedepece in https://github.com/tgalal/yowsup/pull/781
                #modified to support python3
                src = Image.open(path)
                pictureData = src.resize((640, 640)).tobytes("jpeg", "RGB")
                picturePreview = src.resize((96, 96)).tobytes("jpeg", "RGB")
                iq = SetPictureIqProtocolEntity(self.getOwnJid(), picturePreview, pictureData)
                self._sendIq(iq, onSuccess, onError)

    ########### groups

    @clicmd("List all groups you belong to", 5)
    def groups_list(self):
        if self.assertConnected():
            entity = ListGroupsIqProtocolEntity()
            self.toLower(entity)

    @clicmd("Leave a group you belong to", 4)
    def group_leave(self, group_jid):
        if self.assertConnected():
            entity = LeaveGroupsIqProtocolEntity([self.aliasToJid(group_jid)])
            self.toLower(entity)

    @clicmd("Create a new group with the specified subject and participants. Jids are a comma separated list but optional.", 3)
    def groups_create(self, subject, jids = None):
        if self.assertConnected():
            jids = [self.aliasToJid(jid) for jid in jids.split(',')] if jids else []
            entity = CreateGroupsIqProtocolEntity(subject, participants=jids)
            self.toLower(entity)

    @clicmd("Invite to group. Jids are a comma separated list")
    def group_invite(self, group_jid, jids):
        if self.assertConnected():
            jids = [self.aliasToJid(jid) for jid in jids.split(',')]
            entity = AddParticipantsIqProtocolEntity(self.aliasToJid(group_jid), jids)
            self.toLower(entity)

    @clicmd("Promote admin of a group. Jids are a comma separated list")
    def group_promote(self, group_jid, jids):
        if self.assertConnected():
            jids = [self.aliasToJid(jid) for jid in jids.split(',')]
            entity = PromoteParticipantsIqProtocolEntity(self.aliasToJid(group_jid), jids)
            self.toLower(entity)

    @clicmd("Remove admin of a group. Jids are a comma separated list")
    def group_demote(self, group_jid, jids):
        if self.assertConnected():
            jids = [self.aliasToJid(jid) for jid in jids.split(',')]
            entity = DemoteParticipantsIqProtocolEntity(self.aliasToJid(group_jid), jids)
            self.toLower(entity)

    @clicmd("Kick from group. Jids are a comma separated list")
    def group_kick(self, group_jid, jids):
        if self.assertConnected():
            jids = [self.aliasToJid(jid) for jid in jids.split(',')]
            entity = RemoveParticipantsIqProtocolEntity(self.aliasToJid(group_jid), jids)
            self.toLower(entity)

    @clicmd("Change group subject")
    def group_setSubject(self, group_jid, subject):
        if self.assertConnected():
            entity = SubjectGroupsIqProtocolEntity(self.aliasToJid(group_jid), subject)
            self.toLower(entity)

    @clicmd("Set group picture")
    def group_picture(self, group_jid, path):
        if self.assertConnected():
            with PILOptionalModule(failMessage = self.__class__.FAIL_OPT_PILLOW) as imp:
                Image = imp("Image")

                def onSuccess(resultIqEntity, originalIqEntity):
                    self.output("Group picture updated successfully")

                def onError(errorIqEntity, originalIqEntity):
                    logger.error("Error updating Group picture")

                #example by @aesedepece in https://github.com/tgalal/yowsup/pull/781
                #modified to support python3
                src = Image.open(path)
                pictureData = src.resize((640, 640)).tobytes("jpeg", "RGB")
                picturePreview = src.resize((96, 96)).tobytes("jpeg", "RGB")
                iq = SetPictureIqProtocolEntity(self.aliasToJid(group_jid), picturePreview, pictureData)
                self._sendIq(iq, onSuccess, onError)        


    @clicmd("Get group info")
    def group_info(self, group_jid):
        if self.assertConnected():
            entity = InfoGroupsIqProtocolEntity(self.aliasToJid(group_jid))
            self.toLower(entity)

    @clicmd("Get shared keys")
    def keys_get(self, jids):
        with AxolotlOptionalModule(failMessage = self.__class__.FAIL_OPT_AXOLOTL) as importFn:
            importFn()
            from yowsup.layers.axolotl.protocolentities.iq_key_get import GetKeysIqProtocolEntity
            if self.assertConnected():
                jids = [self.aliasToJid(jid) for jid in jids.split(',')]
                entity = GetKeysIqProtocolEntity(jids)
                self.toLower(entity)


    @clicmd("Send prekeys")
    def keys_set(self):
        with AxolotlOptionalModule(failMessage = self.__class__.FAIL_OPT_AXOLOTL) as axoOptMod:
            from yowsup.layers.axolotl import YowAxolotlLayer
            if self.assertConnected():
                self.broadcastEvent(YowLayerEvent(YowAxolotlLayer.EVENT_PREKEYS_SET))

    @clicmd("Send init seq")
    def seq(self):
        priv = PrivacyListIqProtocolEntity()
        self.toLower(priv)
        push = PushIqProtocolEntity()
        self.toLower(push)
        props = PropsIqProtocolEntity()
        self.toLower(props)
        crypto = CryptoIqProtocolEntity()
        self.toLower(crypto)

    @clicmd("Delete your account")
    def account_delete(self):
        if self.assertConnected():
            if self.accountDelWarnings < self.__class__.ACCOUNT_DEL_WARNINGS:
                self.accountDelWarnings += 1
                remaining = self.__class__.ACCOUNT_DEL_WARNINGS - self.accountDelWarnings
                self.output("Repeat delete command another %s times to send the delete request" % remaining, tag="Account delete Warning !!", prompt = False)
            else:
                entity = UnregisterIqProtocolEntity()
                self.toLower(entity)

    @clicmd("Send message to a friend")
    def message_send(self, number, content):
        #if self.assertConnected():
        
        print("~~~~~~~~~~~~~~~~~~ %s" % number)#MODF
        x = self.aliasToJid(number)
        print("%s/%i" % (x,len(x)))
        print(content)
        print(type(content))

        #originalMessage = TextMessageProtocolEntity(content[:127].encode("utf-8") if sys.version_info >= (3,0) else content, to = self.aliasToJid(number))
        originalMessage = TextMessageProtocolEntity(content.encode("utf-8") if sys.version_info >= (3,0) else content, to = self.aliasToJid(number))
        self.toLower(originalMessage)
        """while len(content.encode('latin-1')) > 127:
            TXTFragment = content.encode('latin-1')[:127].decode('latin-1')
            outgoingMessage = TextMessageProtocolEntity(TXTFragment if sys.version_info >= (3,0) else TXTFragment.decode('latin-1'), to = self.aliasToJid(number))
            self.toLower(outgoingMessage)
            sleep(3)
            X = len(TXTFragment)
            content = content[X:]
        if len(content):
            outgoingMessage = TextMessageProtocolEntity(content.encode("utf-8") if sys.version_info >= (3,0) else content, to = self.aliasToJid(number))
            self.toLower(outgoingMessage)"""           
        return originalMessage

    @clicmd("Broadcast message. numbers should comma separated phone numbers")
    def message_broadcast(self, numbers, content):
        if self.assertConnected():
            jids = [self.aliasToJid(number) for number in numbers.split(',')]
            outgoingMessage = BroadcastTextMessage(jids, content)
            self.toLower(outgoingMessage)

    #@clicmd("Send read receipt")
    def message_read(self, message_id):
        pass

    #@clicmd("Send delivered receipt")
    def message_delivered(self, message_id):
        pass

    @clicmd("Send an image with optional caption")
    def image_send(self, number, path, caption = None):
        if self.assertConnected():
            jid = self.aliasToJid(number)
            entity = RequestUploadIqProtocolEntity(RequestUploadIqProtocolEntity.MEDIA_TYPE_IMAGE, filePath=path)
            successFn = lambda successEntity, originalEntity: self.onRequestUploadResult(jid, path, successEntity, originalEntity, caption)
            errorFn = lambda errorEntity, originalEntity: self.onRequestUploadError(jid, path, errorEntity, originalEntity)

            self._sendIq(entity, successFn, errorFn)

    @clicmd("Send audio file")
    def audio_send(self, number, path):
        if self.assertConnected():
            jid = self.aliasToJid(number)
            entity = RequestUploadIqProtocolEntity(RequestUploadIqProtocolEntity.MEDIA_TYPE_AUDIO, filePath=path)
            successFn = lambda successEntity, originalEntity: self.onRequestUploadResult(jid, path, successEntity, originalEntity)
            errorFn = lambda errorEntity, originalEntity: self.onRequestUploadError(jid, path, errorEntity, originalEntity)

            self._sendIq(entity, successFn, errorFn)
    @clicmd("Send typing state")
    def state_typing(self, jid):
        if self.assertConnected():
            entity = OutgoingChatstateProtocolEntity(ChatstateProtocolEntity.STATE_TYPING, self.aliasToJid(jid))
            self.toLower(entity)

    @clicmd("Send paused state")
    def state_paused(self, jid):
        if self.assertConnected():
            entity = OutgoingChatstateProtocolEntity(ChatstateProtocolEntity.STATE_PAUSED, self.aliasToJid(jid))
            self.toLower(entity)

    @clicmd("Sync contacts, contacts should be comma separated phone numbers, with no spaces")
    def contacts_sync(self, contacts):
        if self.assertConnected():
            entity = GetSyncIqProtocolEntity(contacts.split(','))
            self.toLower(entity)

    @clicmd("Disconnect")
    def disconnect(self):
        if self.assertConnected():
            self.broadcastEvent(YowLayerEvent(YowNetworkLayer.EVENT_STATE_DISCONNECT))

    @clicmd("Quick login")
    def L(self):
        if self.connected:
            return self.output("Already connected, disconnect first")
        self.getLayerInterface(YowNetworkLayer).connect()
        return True

    @clicmd("Login to WhatsApp", 0)
    def login(self, username, b64password):
        self.setCredentials(username, b64password)
        return self.L()

    ######## receive #########

    @ProtocolEntityCallback("chatstate")
    def onChatstate(self, entity):
        print('received.')
        print(entity)

    @ProtocolEntityCallback("iq")
    def onIq(self, entity):

        print(entity)
        self.LASTIQ = entity

    @ProtocolEntityCallback("receipt")
    def onReceipt(self, entity):
        self.toLower(entity.ack())

    @ProtocolEntityCallback("ack")
    def onAck(self, entity):
        #formattedDate = datetime.datetime.fromtimestamp(self.sentCache[entity.getId()][0]).strftime('%d-%m-%Y %H:%M')
        #print("%s [%s]:%s"%(self.username, formattedDate, self.sentCache[entity.getId()][1]))
        if entity.getClass() == "message":
            self.output(entity.getId(), tag = "Sent")
            #self.notifyInputThread()

    @ProtocolEntityCallback("success")
    def onSuccess(self, entity):
        self.connected = True
        self.output("Logged in!", "Auth", prompt = False)
        self.notifyInputThread()

    @ProtocolEntityCallback("failure")
    def onFailure(self, entity):
        self.connected = False
        self.output("Login Failed, reason: %s" % entity.getReason(), prompt = False)

    @ProtocolEntityCallback("notification")
    def onNotification(self, notification):
        notificationData = notification.__str__()

        if notificationData:
            self.output(notificationData, tag = "Notification")
        else:
            self.output("From :%s, Type: %s" % (self.jidToAlias(notification.getFrom()), notification.getType()), tag = "Notification")
        if self.sendReceipts:
            self.toLower(notification.ack())

    @ProtocolEntityCallback("message")
    def onMessage(self, message):
        messageOut = ""
        formattedDate = datetime.datetime.fromtimestamp(message.getTimestamp()).strftime('%d-%m-%Y %H:%M')

        if message.getType() == "text":
            message.body = message.body.encode('latin-1', 'ignore').decode('utf-8','ignore') 
            self.MESSAGES.append(message)
            try:
                message.getBody().encode('utf-8')
            except UnicodeEncodeError:
                return

            
            if BOT.window:
                if BOT.window.LOADED: BOT.window.refresh_message()
            
            #self.output(message.getBody(), tag = "%s [%s]"%(message.getFrom(), formattedDate))
            messageOut = self.getTextMessageBody(message)
        elif message.getType() == "media":
            messageOut = self.getMediaMessageBody(message)
        else:
            messageOut = "Unknown message type %s " % message.getType()
            print(messageOut.toProtocolTreeNode())

        sender = message.getFrom() if not message.isGroupMessage() else "%s/%s" % (message.getParticipant(False), message.getFrom())
        output = self.__class__.MESSAGE_FORMAT.format(
            FROM = sender,
            TIME = formattedDate,
            MESSAGE = messageOut if sys.version_info >= (3, 0) else messageOut,
            MESSAGE_ID = message.getId()
            )
        

        #read content of messages!
        if time() - message.getTimestamp() < 130:
            sender = message.getFrom()
            if not message.isGroupMessage():
                participant = 0
            else:
                participant = message.getParticipant(False) 

            BOTSAYS = BOT.read_output(messageOut, sender, participant)
            if BOTSAYS != None:
                if type(BOTSAYS) == list:
                    self.group_kick(sender, participant)
                    BOTSAYS = BOTSAYS[0]

                if BOTSAYS[-3:] == 'jpg':
                    print('sending %s       to %s' % (BOTSAYS, sender))
                    self.image_send(message.getFrom(), BOTSAYS)

                elif BOTSAYS[-3:] == 'wav':
                    self.audio_send(message.getFrom(), BOTSAYS)
                else:
                    
                    self.message_send(message.getFrom().split("@")[0], BOTSAYS)

        #end message custom functionality.

        self.output(output, tag = None, prompt = not self.sendReceipts)

        if self.sendReceipts:
            self.toLower(message.ack())
            self.output("Sent delivered receipt", tag = "Message %s" % message.getId())
        
    def getTextMessageBody(self, message):
        return message.getBody()

    def getMediaMessageBody(self, message):
        if message.getMediaType() in ("image", "audio", "video"):
            return self.getDownloadableMediaMessageBody(message)
        else:
            return "[Media Type: %s]" % message.getMediaType()

    def getDownloadableMediaMessageBody(self, message):
         return "[Media Type:{media_type}, Size:{media_size}, URL:{media_url}]".format(
            media_type = message.getMediaType(),
            media_size = message.getMediaSize(),
            media_url = message.getMediaUrl()
            )

    def doSendImage(self, filePath, url, to, ip = None, caption = None):
        entity = ImageDownloadableMediaMessageProtocolEntity.fromFilePath(filePath, url, ip, to, caption = caption)
        self.toLower(entity)

    def doSendAudio(self, filePath, url, to, ip = None, caption = None):
        entity = AudioDownloadableMediaMessageProtocolEntity.fromFilePath(filePath, url, ip, to)
        self.toLower(entity)

    def __str__(self):
        return "CLI Interface Layer"

    ########### callbacks ############

    def onRequestUploadResult(self, jid, filePath, resultRequestUploadIqProtocolEntity, requestUploadIqProtocolEntity, caption = None):

        if requestUploadIqProtocolEntity.mediaType == RequestUploadIqProtocolEntity.MEDIA_TYPE_AUDIO:
            doSendFn = self.doSendAudio
        else:
            doSendFn = self.doSendImage

        if resultRequestUploadIqProtocolEntity.isDuplicate():
            doSendFn(filePath, resultRequestUploadIqProtocolEntity.getUrl(), jid,
                             resultRequestUploadIqProtocolEntity.getIp(), caption)
        else:
            successFn = lambda filePath, jid, url: doSendFn(filePath, url, jid, resultRequestUploadIqProtocolEntity.getIp(), caption)
            mediaUploader = MediaUploader(jid, self.getOwnJid(), filePath,
                                      resultRequestUploadIqProtocolEntity.getUrl(),
                                      resultRequestUploadIqProtocolEntity.getResumeOffset(),
                                      successFn, self.onUploadError, self.onUploadProgress, async=False)
            mediaUploader.start()

    def onRequestUploadError(self, jid, path, errorRequestUploadIqProtocolEntity, requestUploadIqProtocolEntity):
        logger.error("Request upload for file %s for %s failed" % (path, jid))

    def onUploadError(self, filePath, jid, url):
        logger.error("Upload file %s to %s for %s failed!" % (filePath, url, jid))

    def onUploadProgress(self, filePath, jid, url, progress):
        sys.stdout.write("%s => %s, %d%% \r" % (os.path.basename(filePath), jid, progress))
        sys.stdout.flush()

    def onGetContactPictureResult(self, resultGetPictureIqProtocolEntiy, getPictureIqProtocolEntity):
        # do here whatever you want
        # write to a file
        # or open
        # or do nothing
        # write to file example:
        #resultGetPictureIqProtocolEntiy.writeToFile("/tmp/yowpics/%s_%s.jpg" % (getPictureIqProtocolEntity.getTo(), "preview" if resultGetPictureIqProtocolEntiy.isPreview() else "full"))
        pass

    def __str__(self):
        return "CLI Interface Layer"

    @clicmd("Print this message")
    def help(self):
        self.print_usage()
