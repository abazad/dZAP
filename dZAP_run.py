import os
from threading import *
from time import *
import datetime

from tkinter import *
from yowsup import env
from yowsup.common import YowConstants
from yowsup.layers import YowLayerEvent
from yowsup.stacks import YOWSUP_CORE_LAYERS
from yowsup.stacks import YowStack

from layer import YowsupCliLayer
from yowsup.layers import YowParallelLayer
from yowsup.layers.auth import YowAuthenticationProtocolLayer
from yowsup.layers.coder import YowCoderLayer
from yowsup.layers.network import YowNetworkLayer
from yowsup.layers.protocol_acks import YowAckProtocolLayer
from yowsup.layers.protocol_chatstate import YowChatstateProtocolLayer
from yowsup.layers.protocol_groups import YowGroupsProtocolLayer
from yowsup.layers.protocol_media import YowMediaProtocolLayer
from yowsup.layers.protocol_messages import YowMessagesProtocolLayer
from yowsup.layers.protocol_notifications import YowNotificationsProtocolLayer
from yowsup.layers.protocol_presence import YowPresenceProtocolLayer
from yowsup.layers.protocol_profiles import YowProfilesProtocolLayer
from yowsup.layers.protocol_receipts import YowReceiptProtocolLayer

from bot.core import AUTO_RETRIEVE

#small dispositive to help me strace this shit. disposable..
input('go')

#function to load credentials from the CREDENTIALS file in the same folder as this script.. template:

#phone=*************
#password=***************
def retrieve_credentials():
    if os.path.isfile('CREDENTIALS'):
        _CRED = open('CREDENTIALS', 'r').readlines()
        PH = None
        PASS = None
        for line in _CRED:
            if 'phone' in line:
                PH = line.split('=')
                PH = PH[1].split('\n')[0]
            elif 'password' in line:
                PASS = line.split('=',1)
                PASS = PASS[1].split('\n')[0]

        if (PH) and (PASS):
            return (PH,PASS)

    return ('','')


CREDENTIALS = retrieve_credentials()


#if credentials are not provided by file, this window asks for them.
class auth_window():
    def __init__(self):
        self.run()

    def run (self):
        self.root = Tk()

        self.label_phone = Label(self.root, text='Phone:')
        self.label_phone.grid(column=0, row=0)
        self.label_pass = Label(self.root, text= 'Password:')
        self.label_pass.grid(column=0,row=1)
        self.txt_phone = Text(self.root, width=32, height=1)
        self.txt_phone.grid(column=1,row=0)
        self.txt_pass = Text(self.root, width= 32, height=1)
        self.txt_pass.grid(column=1,row=1)

        self.OK = Button(self.root, text='OK', command=self.auth)
        self.OK.grid(column=0,row=2, columnspan=2, sticky=E+W)

        self.root.wm_title('Authentication')
        self.root.mainloop()

    def auth (self):
        print((self.txt_phone.get('1.0',END),self.txt_pass.get('1.0',END)))
        global CREDENTIALS
        CREDENTIALS = (self.txt_phone.get('1.0',END)[:-1],self.txt_pass.get('1.0',END)[:-1])
        self.root.destroy()


#class for messages to be displayed on the GUI window.
class displayed_message(Frame):

    def __init__(self, FROM, DATE, text_content,master=None):
        Frame.__init__(self, master=master, height = 50)

        self.F_=Label(master=self, text=FROM)
        self.F_.grid(column = 2, row = 0)
        self.S_=Label(master=self, text= " ||| ")
        self.S_.grid(column = 1, row = 0)
        self.D_=Label(master=self,text=DATE)
        self.D_.grid(column = 0, row = 0, sticky=W)

        self.C_=Label(master=self,text=text_content)
        self.C_.grid(column = 0, row = 1, columnspan=2,sticky=W)
        self.S_=Label(master=self,text="            ")
        self.S_.grid(column = 0, row = 2)


#main window (GUI) class. It runs as a thread, to function indepently of the stdout stream generated by yowsup client/stacks.
class window(Thread):
    class group():
        def __init__(self, address, party, subject, index, master):
            self.address = address
            self.subject = subject

            self.label = Label(master)
            self.label['text'] = self.subject
            self.label.grid(column=0, row=index+2)

            self.ACT = Button(master)
            self.ACT['text'] = ' '
            self.ACT['activebackground'] = 'grey'
            self.ACT['command'] = self.activate
            self.ACT['background'] = 'black'
            self.ACT.grid(column=1, row=index+2)

            self.ACTIVE = 0

            self.PARTICIPANTS = party

        def activate(self):
            if self.ACTIVE == 1:
                self.ACTIVE = 0
                self.ACT['background'] = 'black'
                self.ACT['activebackground'] = 'dim grey'
            else:
                self.ACTIVE = 1
                self.ACT['background'] = 'olive drab'
                self.ACT['activebackground'] = 'yellow green'

    class automation():
        def __init__(self, triggerTXT, action):
            self.trigger = triggerTXT
            self.action = action

    def automate_window(self):
        self.auto_window = Tk()
        self.auto_window.VIEW = Canvas(self.auto_window).grid(row=0,column=0)
        self.auto_window.OK = Button(self.auto_window, text="save & close").grid(row=1,column=0)
        self.auto_window.wm_title(self.NAME + " [manage automation]")
        self.auto_window.mainloop()

    def __init__(self):
        Thread.__init__(self)

        self.NAME = 'dZAP'
        self.start()
        self.connected=1
        self.contacts = {}

        self.GROUPS = []

        self.MSGREADINDEX = 0
        self.MSGABSINDEX = 0

        self.YOWCLI = stack.getLayer(6)

        self.SHOWNMESSAGE = []

    def callback(self):
        self.root.quit()

    def sendtext(self,event=None):
        self.refresh_message()
        sent=[]
        CONTENT = self.TEXTIN.get("1.0",END)[:-1]

        for AUTO in AUTO_RETRIEVE:
            if AUTO.TRIGGER_WORD == event:
                print('>>>>'+CONTENT)
                CONTENT = AUTO.retrieve(CONTENT)

        for GROUP in self.GROUPS:
            if GROUP.ACTIVE == 1:
                MSG = self.YOWCLI.message_send(GROUP.address, CONTENT)
                sent.append(GROUP.address)

        self.TEXTIN.delete(1.0, END)
        if len(sent) > 0:
            self.showmessage(MSG, TO = ">>> %s" % sent)

    def run(self):#this function is started on __init___, because the window is a Thread. Initialize GUI and its widgets and menus.
        self.root = Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.callback)
        self.root.resizable(width=FALSE, height=FALSE)

        self.VISOR = Frame(self.root, height = 600, width=500)
        self.VISOR.grid(column=0,row=0,columnspan=4)
        self.VISOR.grid_propagate(False)
        '''for I in range(10):
            self.SHOWNMESSAGE.append(displayed_message(" ", " ", " ", master=self.VISOR))
            self.SHOWNMESSAGE[I].grid(column=0, row=I)'''

        self.TEXTIN = Text(self.root, height=2, width=73)
        self.TEXTIN.grid(column=0,row=1,columnspan=4, sticky=W+E)
        self.SEND = Button(self.root, text = 'SEND', command = lambda: self.sendtext()).grid(column=2,row=2)
        self.SENDVOICE = Button(self.root, text= 'SENDVOICE', command = self.send_voice).grid(column=2,row=3)
        self.REFRESH = Button(self.root, text = 'REFRESH', command = self.getinfo).grid(column=3,row=4)
        self.LOADMSG = Button(self.root, text = 'load MSG', command = self.refresh_message).grid(column=3,row=3)
        self.ADM = Button(self.root, text = 'toADM')
        self.ADM["command"] = lambda: stack.getLayer(6).group_promote(self.GROUPS[2].address, self.TEXTIN.get("1.0",END)[:-1])
        self.ADM.grid(column=3,row=2)
        self.BROWSE = Button(self.root, text= 'browse file')
        self.BROWSE["command"] = lambda: self.browsefiles(self.TEXTIN)
        self.BROWSE.grid(column=2, row=4)

        self.root.wm_title(self.NAME)
        self.menubar = Menu(self.root)

        self.AUTOMATE = Menu(self.menubar)
        self.AUTOMATE.add_command(label="Turn ON/OFF", background="red")
        self.AUTOMATE.add_command(label="MANAGE", command = lambda: self.automate_window())
        self.AUTOMATE.add_separator()
        self.AUTOMATE.add_command(label ="@dict", command = lambda: self.sendtext(event='@dict'))
        self.AUTOMATE.add_command(label ="@indict", command = lambda: self.sendtext(event='@indict'))
        self.AUTOMATE.add_command(label ="@wiki", command = lambda: self.sendtext(event='@wiki'))
        self.AUTOMATE.add_command(label ='Vestibular', command = lambda: BOT.govestibular(self.GROUPS[self.highlighted_group()].address))

        self.PROFILE = Menu(self.menubar)
        self.PROFILE.add_command(label="SET NICK", command = lambda: self.edit_profile('nick'))
        self.PROFILE.add_command(label="SET STATUS",  command = lambda: self.edit_profile('status'))
        self.PROFILE.add_command(label="SET IMAGE", command = lambda: self.edit_profile('image'))

        self.GROUP = Menu(self.menubar)
        self.GROUP.add_command(label="SET GROUP NAME", command = lambda: self.edit_profile('group name'))
        self.GROUP.add_command(label="SET GROUP IMAGE", command = lambda: self.edit_profile('group image'))
        self.GROUP.add_separator()
        self.GROUP.add_command(label="BAN")
        self.GROUP.add_command(label="demote ALL", command = lambda: self.admin_toall(0))
        self.GROUP.add_command(label="promote ALL", command = lambda: self.admin_toall(1))

        self.FILES = Menu(self.menubar)
        self.FILES.add_command(label="SEND IMAGE", command = lambda: self.YOWCLI.image_send(self.GROUPS[self.highlighted_group()].address, self.TEXTIN.get('1.0',END)[:-1]))
        self.menubar.add_cascade(label = "PROFILE", menu = self.PROFILE)
        self.menubar.add_cascade(label = "GROUP", menu = self.GROUP)
        self.menubar.add_cascade(label = "AUTOMATE", menu = self.AUTOMATE)
        self.menubar.add_cascade(label = 'FILES', menu = self.FILES)

        self.root.config(menu=self.menubar)

        sleep(2)
        self.getinfo()

        self.root.mainloop()

    def edit_profileSAVEQUIT(self,attribute):
        if attribute == 'nick':
            self.YOWCLI.presence_name(self.editprofile.TEXT.get('1.0',END))
        elif attribute == 'status':
            self.YOWCLI.profile_setStatus(self.editprofile.TEXT.get('1.0',END))
        elif attribute == 'image':
            self.YOWCLI.profile_setPicture(self.editprofile.TEXT.get('1.0',END)[:-1])
        else:
            for G in self.GROUPS:
                if G.ACTIVE:
                    if attribute == 'group name':
                        self.YOWCLI.group_setSubject(G.address, self.editprofile.TEXT.get('1.0',END)[:-1])
                    elif attribute == 'group image':
                        self.YOWCLI.group_picture(G.address, self.editprofile.TEXT.get('1.0',END)[:-1])

        self.editprofile.destroy()

    def edit_profile(self, attribute):
        self.editprofile = Tk()

        self.editprofile.TEXT = Text(self.editprofile,height=1)
        self.editprofile.TEXT.grid(column=0,row=0)
        self.editprofile.OK = Button(self.editprofile, text="save", command = lambda: self.edit_profileSAVEQUIT(attribute)).grid(column=0,row=1)

        if 'image' in attribute:
            self.editprofile.BROWSE = Button(self.editprofile, text='Browse', command = lambda: self.browsefiles(self.editprofile.TEXT)).grid(column=1,row=0)

        self.editprofile.wm_title('edit %s' % attribute)

    def browsefiles(self, target):#open the file finder dialog.
        target.delete('1.0', END)
        target.insert('1.0', filedialog.askopenfilename(title = "escolha a imagem.",))

    def refresh_message(self):
        while self.MSGREADINDEX < len(stack.getLayer(6).MESSAGES):
            self.showmessage(stack.getLayer(6).MESSAGES[self.MSGREADINDEX])
            self.MSGREADINDEX+=1

    def send_voice(self):#convert text input to synthetized voice, and send the file.
        for GROUP in self.GROUPS:
            if GROUP.ACTIVE == 1:
                create_voice(self.TEXTIN.get("1.0",END))
                sleep(1)
        self.TEXTIN.delete(1.0, END)

    def showmessage(self, message, TO = None):#refresh message viewing visor.
        INDEX = self.MSGABSINDEX*3

        try:
            text_content = message.getBody().decode('utf-8','ignore')
        except AttributeError:
            text_content = message.getBody()

        for K in range(round(len(text_content)/60)):
            text_content = text_content[:60*K] + "\n" + text_content[60*K:]

        if not message.getFrom():
            FROM = TO
        else:
            FROM = message.getFrom()

        DATE = datetime.datetime.fromtimestamp(message.getTimestamp()).strftime('%d-%m-%Y %H:%M')

        self.SHOWNMESSAGE.append(displayed_message(FROM, DATE, text_content, master=self.VISOR))

        if len(self.SHOWNMESSAGE) > 10:
            self.SHOWNMESSAGE.pop(0)

        for M in range(len(self.SHOWNMESSAGE)):
            self.SHOWNMESSAGE[M].grid_forget()
        for M in range(len(self.SHOWNMESSAGE)):
            self.SHOWNMESSAGE[M].grid(column=0,row=M, sticky=W)

        self.MSGABSINDEX+=1

    def getinfo(self):#send group info request.
        stack.getLayer(6).groups_list()
        sleep(2)
        self.process(stack.getLayer(6).LASTIQ)

    def process(self, INFO):#receive and interprete the info we asked to the server in the getinfo() function, to load the GUI with the appropriate buttons.
        #also appends any contact you got on CONTACTS file, so the contacts and groups will appear on the same list on the app.
        try:
            if INFO.getType() == 'result':
                self.GROUPS = []
                I=0

                contacts = open('CONTACTS','r').readlines()

                for line in contacts:
                    if len(line) > 3:
                        person = line[:-1].split(';')
                        self.GROUPS.append(self.group(person[1], [], person[0], I, self.root))
                        I+=1

                for G in INFO.groupsList:
                    PARTY = G.getParticipants()
                    SUBJ = G.getSubject()
                    ID = G.getId()
                    self.GROUPS.append(self.group(ID, PARTY, SUBJ, I, self.root))
                    I+=1
        except AttributeError:
            pass

    def highlighted_group(self):#return the group that is selected on the GUI, if there is exactly one.
        H=[]
        for G in range(len(self.GROUPS)):
            if self.GROUPS[G].ACTIVE == 1:
                H.append(self.GROUPS[G])

        if len(H) == 1:
            return H[0]

    def admin_toall(self, demotepromote):#demote all admins on a group, but yourself.
        group = self.highlighted_group()
        print(group)
        if group:
            party = group.PARTICIPANTS.items()
            for person in party:
                if CREDENTIALS[0] not in person[0]:
                    if demotepromote:
                        if person[1] != 'admin':
                            self.YOWCLI.group_promote(group.address, person[0])
                    else:
                        if person[1] == 'admin':
                            self.YOWCLI.group_demote(group.address, person[0])


if __name__==  "__main__":
    #if credentials are unavailable, launch auth window.
    if len(CREDENTIALS[0]) < 2:
        print(CREDENTIALS[0])
        auth_w = auth_window()

    #initialize yowsup stack, with the layers we need.
    layers = (
        YowsupCliLayer,
        YowParallelLayer(
            [
                YowAuthenticationProtocolLayer,
                YowMessagesProtocolLayer,
                YowReceiptProtocolLayer,
                YowAckProtocolLayer,
                YowGroupsProtocolLayer,
                YowProfilesProtocolLayer,
                YowChatstateProtocolLayer,
                YowPresenceProtocolLayer,
                YowMediaProtocolLayer,
                YowNotificationsProtocolLayer,
            ]
        )
    ) + YOWSUP_CORE_LAYERS

    stack = YowStack(layers)
    stack.setProp(YowAuthenticationProtocolLayer.PROP_CREDENTIALS, CREDENTIALS)         #setting credentials
    stack.setProp(YowNetworkLayer.PROP_ENDPOINT, YowConstants.ENDPOINTS[0])    #whatsapp server address
    stack.setProp(YowCoderLayer.PROP_DOMAIN, YowConstants.DOMAIN)
    stack.setProp(YowCoderLayer.PROP_RESOURCE, env.CURRENT_ENV.getResource())          #info about us as WhatsApp client
    stack.broadcastEvent(YowLayerEvent(YowNetworkLayer.EVENT_STATE_CONNECT))   #sending the connect signal

    #setting bot and cli layer to know each other.
    BOT = stack.getLayer(6).getBot()
    BOT.getCliLayer(stack.getLayer(6))

    #starting the GUI and client; set BOT to recognize the window instance.
    app = window()
    BOT.window = app
    stack.loop()
