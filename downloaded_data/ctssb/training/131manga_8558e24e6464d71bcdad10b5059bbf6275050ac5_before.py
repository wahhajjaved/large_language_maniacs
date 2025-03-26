# -*- coding:gbk -*-
'''
注：这个文件在编译exe的时候要改名为131manhua，因为setup.py里面不能有中文
'''
from tkinter import *
from tkinter import font
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
from PIL import Image,ImageTk
import os,sys
from tkinter.filedialog import askdirectory
import threading
from multiprocessing import Process,Pipe,freeze_support
import parse_131
import httplib2
import download_131
import webbrowser

class MyDownloadProcess(Process):
    #使下载的时候不阻塞tk的正常loop.单部漫画下载进程
    def __init__(self,url,dirname,dontdownloadlist,webtype,pipeout):#tkinter的控件不能被pickle
        self.url = url
        self.dir = dirname
        self.webtype = webtype
        self.pipeout = pipeout    #匿名管道的写入端
        self.buttonlist = []
        self.dontdownloadlist = dontdownloadlist   #不下载的分卷列表
        Process.__init__(self)
        
    def run(self):
        test = download_131.download_131(self.url,self.dir,self.webtype,self.pipeout,self.dontdownloadlist)
        test.finaldownload()
        os.system('rd /S /Q %s'%('.cache'))  #用系统命令删除cache文件夹
        temp = '1000'
        self.pipeout.send(temp)        
        sys.stdout.flush()   
        sys.stderr.flush()

class MyDownloadProcess_many(Process):
    #多部漫画下载进程
    def __init__(self,url_list,name_list,dirname,webtype,pipeout):
        self.url_list = url_list
        self.name_list = name_list
        self.dir = dirname
        self.webtype = webtype
        self.pipeout = pipeout    #匿名管道的写入端
        Process.__init__(self)
    
    def run(self):
        for url in self.url_list:
            temp = 'name ' + self.name_list[self.url_list.index(url)] #获取当前下载的漫画的名称,发过去
            self.pipeout.send(temp)
            test = download_131.download_131(url,self.dir,self.webtype,self.pipeout)
            test.finaldownload() 
            if url == self.url_list[-1]:
                temp = '1000'
            else:
                temp = '100'
            self.pipeout.send(temp)
        os.system('rd /S /Q %s'%('.cache'))  #用系统命令删除cache文件夹
        sys.stdout.flush()   
        sys.stderr.flush()

def progressbar(pipein,progress,showstate):
    from time import clock
    k = 0
    while True:
        content = pipein.recv()
        if content.startswith('name '):
            showstate['text'] = '正在下载' + content.split()[1]
        else:
            schedule = float(content)
            if schedule > 0 and k == 0:
                k = 1
                start = clock()
            if schedule <= 1:
                progress['value'] = 100 * schedule  #必须写['value']，.value不行
            elif schedule < 500:    #针对多部漫画下载时,下载完其中一部并不需要退出progressbar线程
                pass
            else:
                end = clock()
                showstate['text'] = '下载完毕，共耗时%d秒'%(end-start)
                progress['value'] = 100
                break
  

class GUI:
    def __init__(self):
        self.edition = 2.0
        self.tk = Tk()
        self.notebook = ttk.Notebook(self.tk)
        self.notebook.grid(column=0,columnspan=2,row=0)
        self.pane1 = Frame(self.notebook)    #把单部漫画下载放在第一个pane里面
        self.pane2 = Frame(self.notebook)    #第二个pane是多部漫画下载
        self.tk.resizable(0, 0)
        self.tk.title('131漫画下载器')
        self.tk.iconbitmap('icon2.ico')
        self.dirname = ''
        
        self.notebook.add(self.pane1,text='单部漫画下载')
        self.notebook.add(self.pane2,text='多部漫画下载')
        
        self.url = Entry(self.pane1,width=60)
        self.url.grid(row=0,column=0,columnspan=3,padx=(10,5),pady=5,sticky=W+E)
        
        '''pane1左侧的封面图片'''
        self.cover = Canvas(self.pane1,height=320,width=240)
        self.cover.grid(row=1,column=0,rowspan=2,padx=(9,0),sticky=W)
        img = Image.open('img/mr.jpg')
        img = ImageTk.PhotoImage(img)
        self.cover.create_image(0,0,image=img,anchor=NW)    
        '''
        pane1右侧的漫画分卷列表,下面几行代码来自stackoverflow
                这一段说明了把scrollbar绑定到控件上的方法,即设定widget的x/yscrollcommand属性为sb.set
                和sb的command属性为widget.x/yview
                另,很重要的一点是,不要用pack来把sb放到控件上,而应该让sb和控件有同样的等级(即parent相同),
                让后用grid进行对齐
        '''
        self.directory = Text(self.pane1,width=23,height=22,cursor='arrow')
        self.vsb = Scrollbar(self.pane1,orient="vertical")
        self.directory.config(yscrollcommand=self.vsb.set)
        self.vsb.config(command=self.directory.yview)
        self.directory.grid(column=1,row=1,sticky=N+S+E+W,padx=(4,0),pady=(1,0))
        self.vsb.grid(column=2,row=1,sticky=N+S,padx=(0,5),pady=1)
        self.l_chkbuttons = []    #保存button的list,有两个,对应两列
        self.r_chkbuttons = []
        self.l_start = 0
        self.r_start = 0
        '''pane1右侧的全选/反选checkbox'''
        self.quicksel = Canvas(self.pane1)
        self.quicksel.grid(row=2,column=1)
        self.var_selall = IntVar()
        self.var_selall.trace('w',lambda name,index,op,x=self.var_selall: self.do_selall(x))
        self.selall = Checkbutton(self.quicksel,text='全选',var=self.var_selall)
        self.selall.pack(side=LEFT,fill=BOTH)
        self.var_inversesel = IntVar()
        self.var_inversesel.trace('w',self.do_inversesel)
        self.inversesel = Checkbutton(self.quicksel,text='反选',var=self.var_inversesel)
        self.inversesel.pack(side=LEFT,fill=BOTH)
        self.seltip = Label(self.quicksel,text='试试用shift来选择',fg='lightblue')
        self.seltip.pack(side=LEFT)
        
        '''pane2'''
        self.list = Listbox(self.pane2,selectmode=EXTENDED,width=67,height=20,activestyle='none',bd=0)
        self.list.grid(row=0,column=0,sticky=N+S+W+E)
        self.sb2 = Scrollbar(self.pane2,command=self.list.yview, orient='vertical')
        self.list.config(yscrollcommand=self.sb2.set)
        self.sb2.grid(row=0,column=1,sticky=N+S)
        
        self.popup = Menu(self.list,tearoff=0)    #listbox上的右键弹出菜单
        self.popup.add('command',label='删除',command=self.delete)
        self.popup.add('command',label='全部清除',command=self.delete_all)
        self.list.bind('<Button-3>',self.do_popup)
        
        self.button1 = Button(self.tk,text='选择存储路径',command=self.choosedir,width=7)
        self.button1.grid(row=1,column=0,padx=(10,0),pady=5,sticky=W+S+N+E)
        
        self.storedir = Entry(self.tk,text='',width=33)
        self.storedir.grid(row=1,column=1,padx=10,pady=5,sticky=W+E+S+N)
        
        self.showstate = Label(self.tk,text='',font=('宋体', 10))
        self.showstate.grid(row=2,column=1,ipadx=10,ipady=5,sticky=W)
        
        self.progress = ttk.Progressbar(self.tk,orient="horizontal",mode="determinate")
        self.progress.grid(row=3,column=1,padx=10,pady=5,sticky=W+N+S+E)
        self.progress["maximum"] = 100  #maximum必须定义！不然是不存在的！
       
        self.button2 = Button(self.tk,text='开始下载',width=7,command=self.download)
        self.button2.grid(row=2,rowspan=2,column=0,pady=5,padx=(10,0),sticky=W+S+N+E)
        
        '''在提示中显示最新版本'''
        h = httplib2.Http('.cache')
        edition_latest = h.request('http://42.120.19.204/download/edition.txt')[1].decode()
        if float(edition_latest) > self.edition:
            f = font.Font(self.showstate,self.showstate.cget('font'))#从SO考的代码,获取控件中的字体
            f.configure(underline = True)
            self.showstate.configure(font=f,)
            self.showstate.config(text='有新版本,点击查看',fg='blue') 
            self.showstate.bind('<Button-1>',self.getnewversion)
        else:
            self.showstate.config(text='已是最新版本')
        
        self.last_content = ''  #存储剪贴板之前那次的内容,防止加入重复的漫画
        self.tk.after(2000,lambda:self.watch_clipboard())
        self.tk.protocol("WM_DELETE_WINDOW", self.winclose) #当点击关闭窗口时的操作
        self.tk.mainloop()
    
    def getnewversion(self,event):
        webbrowser.open('http://bbs.131.com/thread-2607756-1-1.html')
        f = font.Font(self.showstate,self.showstate.cget('font'))#从SO考的代码,获取控件中的字体
        f.configure(underline = False)
        self.showstate.configure(font=f)
        self.showstate.config(fg='black') 
        self.showstate.unbind('<Button-1>')
        self.showstate.config(text='若链接失效,请直接到帖子里下载')
    
    def winclose(self):
        if messagebox.askokcancel("Quit", "退出131漫画下载?"):
            if os.path.exists('cover.jpg'):
                os.remove('cover.jpg')  #删除之前保存的封面图片
            self.tk.destroy()
    
    def watch_clipboard(self):  
        '''
        http://comic.131.com/content/shaonian/16051.html
                监视剪贴板，要筛选出这样的URL然后自动贴到相应的位置，标准如下：
            (1) 先把http://踢掉，然后用'/'分割，长度为4
            (2) 第一段是comic.131.com
            (3) 第二段是content
        '''
        content = '' 
        ifadd = 0
        try:
            content = self.tk.clipboard_get()
        except TclError:
            pass
        parts = content.lstrip('http://').split('/')
        if self.last_content != content:
            if len(parts) == 4:
                if parts[0] == 'comic.131.com':
                    if parts[1] == 'content':
                        self.last_content = content
                        self.tk.clipboard_clear()
                        ifadd = messagebox.askokcancel('','将这部漫画加入下载列表？',default='ok')#选ok返回True
        if ifadd:
            self.showstate.config(text='正在分析漫画结构,请稍等')
            temp_instance = parse_131.parse131(content)
            h = httplib2.Http('.cache')
            data = h.request(content)[1].decode()   #写入图片用二进制数据就行无需解码,但是feed要解码
            temp_instance.feed(data)
            
            '''根据当前选定的tab决定URL粘贴的位置'''
            if self.notebook.select() == str(self.pane1):#利用windowname来判断选择的pane
                self.l_chkbuttons = []
                self.r_chkbuttons = []
                self.directory.delete('1.0', END)   #1.0代表第一行第一列的字符,这里的'字符'就是checkbox
                self.url.delete(0,END)
                self.url.insert(0,content + ' ' + temp_instance.comicname)    #插入entry
                img = open('cover.jpg','wb')
                cover_data = h.request(temp_instance.coverimage)[1]
                img.write(cover_data)
                img.close()           
                img = Image.open('cover.jpg')#这里用到PIL库,因为tk自带的PhotoImage无法打开jpg
                img = ImageTk.PhotoImage(img)
                self.cover.image = img  #如果不加这一句会无法显示,原因参见笔记《The Tkinter PhotoImage Class》
                self.cover.create_image(0,0,image=img,anchor=NW)
                '''把分卷信息写入self.directory,实际是插入一堆checkbox到directory里.根据分卷数目的奇偶性,略有差别'''
                volumes = list(temp_instance.manga.keys())
                volumes.sort()  #注意,sort是修改原来的list
                amount = len(volumes)   #分卷数
                should_add = int(amount/2 if amount%2==0 else (amount+1)/2)  #两列显示,同行右边列序号比左边大多少
                i = 0
                for i in range(should_add-1):
                    tempvar1 = IntVar()
                    tempvar2 = IntVar()
                    cb_left = Checkbutton(self.directory,padx=0,pady=0,bd=0,text=volumes[i],bg='white',var=tempvar1)
                    cb_left.var = tempvar1  #如果不这样绑定,则因为tempvar是局部变量,出了循环之后就unbind了,var属性也没了。和图片一样。
                    self.l_chkbuttons.append(cb_left)
                    cb_left.bind('<Button-1>', self.l_selstart)         #处理shift选择的函数
                    cb_left.bind('<Shift-Button-1>', self.l_selrange)
                    cb_right = Checkbutton(self.directory,padx=0,pady=0,bd=0,text=volumes[i+should_add],bg='white',var=tempvar2)
                    cb_right.var = tempvar2
                    self.r_chkbuttons.append(cb_right)
                    cb_right.bind('<Button-1>', self.r_selstart)         #处理shift选择的函数
                    cb_right.bind('<Shift-Button-1>', self.r_selrange)
                    self.directory.window_create("end", align=TOP, window=cb_left)
                    self.directory.insert("end",'  ')
                    self.directory.window_create("end", align=TOP, window=cb_right)
                    self.directory.insert("end", "\n") # 强制换行
                    i = i + 1
                tempvar1 = IntVar()
                cb_left = Checkbutton(self.directory,padx=0,pady=0,bd=0,text=volumes[i],bg='white',var=tempvar1)
                cb_left.var = tempvar1
                self.directory.window_create("end", align=TOP, window=cb_left)
                self.l_chkbuttons.append(cb_left)
                cb_left.bind('<Button-1>', self.l_selstart)
                cb_left.bind('<Shift-Button-1>', self.l_selrange)
                if (i+1)*2 <= amount:    #amount是偶数的情况
                    tempvar2 = IntVar()
                    cb_right = Checkbutton(self.directory,padx=0,pady=0,bd=0,text=volumes[i+should_add],bg='white',var=tempvar2)
                    cb_right.var = tempvar2
                    self.directory.insert("end",'  ')
                    self.directory.window_create("end", align=TOP, window=cb_right)
                    self.r_chkbuttons.append(cb_right)
                    cb_right.bind('<Button-1>', self.r_selstart)         #处理shift选择的函数
                    cb_right.bind('<Shift-Button-1>', self.r_selrange)
                self.directory.insert("end", "\n") # to force one checkbox per line
                self.showstate.config(text='分卷解析完毕')
                
            if self.notebook.select() == str(self.pane2):
                self.list.insert(END,content + ' ' + temp_instance.comicname)   #插入列表
                self.showstate.config(text='分卷解析完毕')
        
        self.tk.after(1000, self.watch_clipboard) 
    
    def l_selstart(self,event): #当在分卷列表中选择之后,设定起始点,以便能够用shift选择
        self.l_start = self.l_chkbuttons.index(event.widget)#index函数返回在列表中的序号
    
    def l_selrange(self,event):#根据之前获得的起始点和现在的点击位置,决定改变哪些cb的状态
        start = self.l_start
        end = self.l_chkbuttons.index(event.widget)
        sl = slice(min(start, end)+1, max(start, end))
        for cb in self.l_chkbuttons[sl]:
            cb.toggle()
        self.l_start = end
        
    def r_selstart(self,event):
        self.r_start = self.r_chkbuttons.index(event.widget)
    
    def r_selrange(self,event):
        start = self.r_start
        end = self.r_chkbuttons.index(event.widget)
        sl = slice(min(start, end)+1, max(start, end))
        for cb in self.r_chkbuttons[sl]:
            cb.toggle()
        self.r_start = end
        
    def do_selall(self,arg):    
        '''点击或取消点击'全选'按钮时的操作'''
        state = arg.get()
        if state:
            for item in self.l_chkbuttons:
                item.select()
            for item in self.r_chkbuttons:
                item.select()
        else:
            for item in self.l_chkbuttons:
                item.deselect()
            for item in self.r_chkbuttons:
                item.deselect()
                
    def do_inversesel(self,*args):    
        for item in self.l_chkbuttons:
            item.toggle()
        for item in self.r_chkbuttons:
            item.toggle()
    
    def do_popup(self,event):#多部漫画下载列表的右键弹出菜单
        self.popup.post(event.x_root, event.y_root) #用x_root,y_root，不要用x,y
    
    def delete(self):
        '''删除list中选中的条目'''
        sel_list = self.list.curselection() #selection_get()会返回选中文字
        i = 0
        for index in sel_list:
            index = int(index)      #注意返回的sel_list的元素都是str
            index = index - i       #每次删除一个，剩下的index都应该-1
            self.list.delete(index)
            i = i + 1
    
    def delete_all(self):
        '''删除list中的全部条目'''
        self.list.delete(0, END)
                
    def choosedir(self):
        self.storedir['state'] = NORMAL
        self.storedir.delete(0, END)
        self.dirname = askdirectory()
        self.storedir.insert(0, self.dirname)
        self.storedir['state'] = 'readonly' #'readonly'是可选不可改，DISABLED直接无法选择
    
    def download(self):
        self.progress['value'] = 0
        if self.dirname == '':
            self.showstate['text'] = '请选择漫画保存的路径'
            return
        if self.notebook.select() == str(self.pane1):#单部漫画下载
            if self.url.get() == '':
                self.showstate.config(text = '请输入漫画主页面的地址')
                return
            pipein,pipeout = Pipe()
            threading.Thread(target=progressbar,daemon=True,args=(pipein,self.progress,self.showstate)).start()
            text_in_entry = self.url.get()  #url后面有漫画的名字,split后取[0]即是真正url
            url = text_in_entry.split()[0]
            buttonlist = []
            dontdownloadlist = []
            buttonlist.extend(self.l_chkbuttons)
            buttonlist.extend(self.r_chkbuttons)
            for button in buttonlist:
                state = button.var.get()
                if not state:
                    dontdownloadlist.append(button['text'])
            download_process = MyDownloadProcess(url,self.dirname,dontdownloadlist,'131',pipeout)
            download_process.daemon = True
            self.showstate['text'] = 'downloading……'
            download_process.start() #只要不用join，则不会阻塞原来的线程
            
        elif self.notebook.select() == str(self.pane2):#多部漫画下载
            url_list = list(self.list.get(0,END))
            name_list = []  #存储漫画的名字,在显示提示行的时候用,让用户知道他在下的是哪一部漫画。
            for i in range(len(url_list)):
                name_list.append(url_list[i].split()[1])
                url_list[i] = url_list[i].split()[0]  #同样是取第一部分
            pipein,pipeout = Pipe()
            threading.Thread(target=progressbar,daemon=True,args=(pipein,self.progress,self.showstate)).start()
            download_process = MyDownloadProcess_many(url_list,name_list,self.dirname,'131',pipeout)
            download_process.daemon = True
            self.showstate['text'] = 'downloading……'
            download_process.start() 



if __name__ == '__main__':
    freeze_support()
    gui = GUI()
