'''
Baby Gene
PSIT Project
By Tharathip Malaimarn(tharamalai=>nam)
    Pawarisa Thong-ngoen(Jessegade=>gade)
APPLICATION to tell you
- probability of gene's your baby
--Blood Group
--Genetic Diseases
************it only probability************
'''

import Tkinter as tk
from PIL import ImageTk, Image
import tkMessageBox

class Home(object):
    def __init__(self,root):
        self.root = root
        self.main()

    def main(self):
        self.root.geometry("430x650")
        self.root.title('Baby Gene')
        image = Image.open('bg.jpg')
        tkimage = ImageTk.PhotoImage(image)
        bg = tk.Label(self.root, image = tkimage)
        bg.place(x=0, y=0, relwidth=1, relheight=1)
        bdg = lambda : Family(self.root,'Blood Group', 'BD')
        bloodgroup = tk.Button(self.root, text='Blood Type', command=bdg, bg='white').place(x=180, y=112)

        ar = tk.Label(self.root, text='AUTOSOME RECESSIVE').place(x=150, y=145)
        semia = lambda : Family(self.root,'Thalassemia', 'AR')
        thalas = tk.Button(self.root, text='Thalassemia', command=semia, bg='white').place(x=177, y=165)
        tose = lambda : Family(self.root, 'Galactosemia', 'AR')
        galac = tk.Button(self.root, text='Galactosemia', command=tose, bg='white').place(x=173, y=191)
        sis = lambda : Family(self.root, 'Cystic Fibrosis', 'AR')
        cystic = tk.Button(self.root, text='Cystic Fibrosis', command=sis, bg='white').place(x=171, y=217)
        alb = lambda : Family(self.root, 'Albinism', 'AR')
        albin = tk.Button(self.root, text='Albinism', command=alb, bg='white').place(x=188, y=243)

        ad = tk.Label(self.root, text='AUTOSOME DOMINANT').place(x=150, y=280)
        asia = lambda : Family(self.root, 'Achondroplasia', 'AD')
        acon = tk.Button(self.root, text='Achondroplasia', command=asia, bg='white').place(x=173, y=302)
        ome = lambda : Family(self.root, 'Marfan Syndrome', 'AD')
        marfan = tk.Button(self.root, text='Marfan Syndrome', command=ome, bg='white').place(x=163, y=328)
        mato = lambda : Family(self.root, 'Neurofibromatosis', 'AD')
        neuro = tk.Button(self.root, text='Neurofibromatosis', command=mato, bg='white').place(x=161, y=354)
        rea = lambda : Family(self.root, "Huntingron's chorea", 'AD')
        hunti = tk.Button(self.root, text="Huntingron's chorea", command=rea, bg='white').place(x=156, y=380)
        
        xlink = tk.Label(self.root, text='X-LINKED RECESSIVE').place(x=160, y=417)
        ness = lambda : Family(self.root, 'Color Blindness', 'XL')
        color = tk.Button(self.root, text='Color Blindness', command=ness, bg='white').place(x=172, y=439)
        lia = lambda : Family(self.root, 'Hemophilia', 'XL')
        hemo = tk.Button(self.root, text='Hemophilia', command=lia, bg='white').place(x=180, y=465)
        pd = lambda : Family(self.root, 'G-6-PD deficieccy', 'XL')
        g6 = tk.Button(self.root, text='G-6-PD deficieccy', command=pd, bg='white').place(x=166, y=491)
        nne = lambda : Family(self.root, "Duchenne's muscular dystrophy", 'XL')
        duch = tk.Button(self.root, text="Duchenne's muscular dystrophy", command=nne, bg='white').place(x=126, y=517)
        dro = lambda : Family(self.root, "Hypohidrotic ectodermal dysplasia", 'XL')
        hypo = tk.Button(self.root, text="Hypohidrotic ectodermal dysplasia", command=dro, bg='white').place(x=118, y=543)
        
        quit_image = ImageTk.PhotoImage(Image.open('quitbutton.png'))
        quit_button = tk.Button(self.root,command=self.end,image=quit_image,border=0)
        quit_button.place(x=170, y=600)

        self.root.mainloop()

    def end(self):
        self.root.destroy()
        
class Choice(tk.OptionMenu):
 def __init__(self, root, *lst):
    show = tk.Label(self.root, text=text).place(x=nx, y=ny)
    self.var = StringVar(root)
    self.var.set('NORMAL')
    tk.OptionMenu.__init__(self, root, self.var, *lst)
    self.config(bg='white')
        
class Family(object):
    '''
    input
    Family(root, name)
    '''
    def __init__(self, root, name, code):
        self.keep = dict()
        self.name = name
        self.root = root
        self.code = code
        self.poo = tk.StringVar(self.root)
        self.yaa = tk.StringVar(self.root)
        self.taa = tk.StringVar(self.root)
        self.yay = tk.StringVar(self.root)
        self.dad = tk.StringVar(self.root)
        self.mom = tk.StringVar(self.root)
        self.tree()

    def choice(self, who, text, lst, nx, ny, bx, by):
        show = tk.Label(self.root, text=text).place(x=nx, y=ny)
        who.set('SELECT')
        who_type = tk.OptionMenu(self.root, who, *lst, command=lambda var=who.get(), text=text: self.add(var, text))
        who_type.config(bg='white')
        who_type.place(x=bx, y=by)

    def add(self, var, text):
        self.keep[text] = var

    def tree(self):
        self.root.geometry("430x650")
        image = Image.open('win1.jpg')
        tkimage = ImageTk.PhotoImage(image)
        bg = tk.Label(self.root, image = tkimage)
        bg.place(x=0, y=0, relwidth=1, relheight=1)

        diseasedname = tk.Label(self.root, text=self.name.upper()).place(x=105, y=0)

        global poo, yaa, taa, yay, dad, mom

        if self.code == 'AR':
            lst = ['NORMAL', 'DISEASED', 'CARRIER']
        elif self.code == 'AD':
            lst = ['NORMAL', 'DISEASED']
        else:
            lst = ['A', 'B', 'AB', 'O']
            
        self.poo = self.choice(self.poo, "Grandfather(DADDY)", lst, 70, 50, 60, 70)
        self.yaa = self.choice(self.yaa, "Grandmother(DADDY)", lst, 280, 50, 270, 70)
        self.taa = self.choice(self.taa, "Grandfather(MOMMY)", lst, 70, 190, 60, 210)
        self.yay = self.choice(self.yay, "Grandmother(MOMMY)", lst, 280, 190, 270, 210)
        self.dad = self.choice(self.dad, "Daddy", lst, 190, 120, 165, 140)
        self.mom = self.choice(self.mom, "Mommy", lst, 190, 280, 165, 300)
          
        process_image = ImageTk.PhotoImage(Image.open('processbutton.png'))
        process_button = tk.Button(self.root,command=self.bus,image=process_image,border=0)
        process_button.place(x=140, y=400)
        self.root.mainloop()
        
    def bus(self):
        st = {'DISEASED':'D', 'NORMAL':'N', 'CARRIER':'C', 'A':'AA', 'B':'BB', 'AB':'AB', 'O':'ii'}
        self.poo, self.yaa, self.dad = st[self.keep["Grandfather(DADDY)"]], st[self.keep["Grandmother(DADDY)"]], st[self.keep["Daddy"]]
        self.taa, self.yay, self.mom = st[self.keep["Grandfather(MOMMY)"]], st[self.keep["Grandfather(MOMMY)"]], st[self.keep["Mommy"]]
        if self.code == 'AR':
            self.autosomerecessive(self.root)
        elif self.code == 'AD':
            self.autosomedominant(self.root)
        elif self.code == 'XL':
            self.xlink(self.root)
        elif self.code == 'BD':
            self.blood(self.root)     

    def cross(self, male, female, code, re):
        if code == 'AR':
            gtab = {'D':'aa', 'C':'Aa', 'N': 'AA'}
        elif code == 'AD':
            gtab = {'N':'aa', 'D': 'AA', 'C':'Aa'}
        elif code == 'XL':
            gtabmale = {'N':'XY', 'D':'Yx'}
            gtabfemale = {'N':'XX', 'C':'Xx', 'D':'xx'}
        elif code == 'BD':
            gtab = {'AA':'AA', 'Ai':'Ai', 'BB':'BB', 'Bi':'Bi', 'AB':'AB', 'ii':'ii'}
        genotype = dict()
        if code == 'XL':
            male, female = gtabmale[male], gtabfemale[female]
        else:
            male, female = gtab[male], gtab[female]
        for s in male:
            for e in female:
                geno = [s, e]
                geno.sort()
                geno = geno[0] + geno[1]
                if geno in genotype:
                    genotype[geno] += 1
                else:
                    genotype[geno] = 1
        print genotype
        if code == 'AR':
            if re == 'check':
                if 'aa' in genotype:
                    return 'D'
                elif 'Aa' in genotype:
                    return 'C'
                else:
                    return 'N'
            else:
                return genotype
        elif code == 'AD':
            if re == 'check':
                if 'AA' in genotype:
                    return 'D'
                else:
                    return 'C'
            else:
                return genotype
        elif code == 'XL':
            if re == 'check':
                if 'Xx' in genotype:
                    return 'C'
                else:
                    return 'N'
            else:
                return genotype
        elif code == 'BD':
            if re == 'check':
                if 'Ai' in genotype:
                    return 'Ai'
                elif 'Bi' in genotype:
                    return 'Bi'
                elif 'AA' or 'BB' in genotype:
                    return genotype.keys()[0]
            else:
                return genotype
    def blood(self, root):
        print self.poo, self.yaa, self.taa, self.yay, self.dad, self.mom, self.code
        if (self.dad == 'AA' and (self.poo != 'AB' and self.yaa != 'AB')) or \
            (self.dad == 'BB' and (self.poo != 'AB' and self.yaa != 'AB')):
            self.dad = self.cross(self.poo, self.yaa, self.code, 'check')
            
        print self.dad
        if (self.mom == 'AA' and (self.taa != 'AB' and self.yay != 'AB')) or \
            (self.mom == 'BB' and (self.taa != 'AB' and self.yay != 'AB')):
            self.mom =  self.cross(self.taa, self.yay, self.code, 'check')
        print self.mom
        baby = baby = self.cross(self.dad, self.mom, self.code, 'baby')
        print_result = Result(root, baby, self.name, self.code)
           
    def autosomerecessive(self, root):
        print self.poo, self.yaa, self.taa, self.yay, self.dad, self.mom, self.code
        if self.dad == 'N':
            self.dad = self.cross(self.poo, self.yaa, self.code, 'check')
            if self.dad == 'D':
                self.dad = 'C'
        print self.dad
        if self.mom == 'N':
            self.mom = self.cross(self.taa, self.yay, self.code, 'check')
            if self.mom == 'D':
                self.mom = 'C'
        print self.mom
        baby = self.cross(self.dad, self.mom, self.code, 'baby')
        print_result = Result(root, baby, self.name, self.code)

    def autosomedominant(self, root):
        print self.poo, self.yaa, self.taa, self.yay, self.dad, self.mom, self.code
        if self.dad == 'D':
            self.dad = self.cross(self.poo, self.yaa, self.code, 'check')
        print self.dad
        if self.mom == 'D':
            self.mom = self.cross(self.taa, self.yay, self.code, 'check')
        print self.mom
        baby = self.cross(self.dad, self.mom, self.code, 'baby')
        print_result = Result(root, baby, self.name, self.code)

    def xlink(self, root):
        print self.poo, self.yaa, self.taa, self.yay, self.dad, self.mom, self.code
        if self.mom == 'N':
            self.mom = self.cross(self.taa, self.yay, self.code, 'check')
        print self.dad
        print self.mom
        baby = self.cross(self.dad, self.mom, self.code, 'baby')
        print_result = Result(root, baby, self.name, self.code)

class Result(object):
    def __init__(self, root ,baby, name, code):
        self.root = root
        self.baby = baby
        self.name = name
        self.code = code
        self.print_gene()
    def print_gene(self):

        self.root.geometry("430x650")
        image = Image.open('win1.jpg')
        tkimage = ImageTk.PhotoImage(image)
        bg = tk.Label(self.root, image = tkimage)
        bg.place(x=0, y=0, relwidth=1, relheight=1)
        
        self.head = tk.Label(self.root, text=self.name.upper()).place(x=150, y=20)
        picdisease = {'Thalassemia':"thalassemia.png", 'Galactosemia':"galac.png",
                      'Cystic Fibrosis':"cystic.png", 'Albinism':"albinism.png",
                      'Achondroplasia':"achondro.png", 'Marfan Syndrome':"marfan.png",
                      'Neurofibromatosis':"neuro.png", "Huntingron's chorea":"hunting.png",
                      'Color Blindness':"color.png", 'Hemophilia':"hemophilia.png",
                      'G-6-PD deficieccy':"g6pd.png", "Duchenne's muscular dystrophy":"duchen.png",
                      "Hypohidrotic ectodermal dysplasia":"hypo.png", "Blood Group":"blood.png"}
        imagee = Image.open(picdisease[self.name])
        photo = ImageTk.PhotoImage(imagee)
        label = tk.Label(image=photo)
        label.image = photo 
        label.place(x=20, y=50)
    
        yourbaby = tk.Label(self.root, text=self.predict()).place(x=150,y=280)

        image = Image.open('backbutton.png')
        back_image = ImageTk.PhotoImage(image)
        back_button = tk.Button(self.root,command=self.back,image=back_image,border=0)
        
        back_button.place(x=150,y=430)
        self.root.mainloop()
    def predict(self):
        if self.code == 'AR':
            didic = {'aa':self.name+' Diseased', 'Aa':self.name+' Carrier', 'AA':' Normal'}
        elif self.code == 'AD':
            didic = {'aa':' Normal', 'Aa':self.name+' Diseased(hetero)', 'AA':self.name+' Diseased(homo)'}
        elif self.code == 'XL':
            didic = {'Yx':self.name +' Diseased Son', 'XY':' Normal Son',
                    'XX':' Normal Daughter', 'Xx':' Normal(carrier) Daughter',
                    'xx':self.name +' Diseased Daughter'}
        elif self.code == 'BD':
            didic = {'AA':'A Homozygous(pure)', 'Ai':'A Heterozygous(hybrid)',
                     'BB':'B Homozygous(pure)', 'Bi':'B Heterozygous(hybrid)',
                     'AB':'AB Homozygous(pure)', 'ii':'O Homozygous(pure)'}
        string = "\nyour baby's gene is \n\n"
        if self.code == 'XL':
            son, daughter = list(), list()
            for item in self.baby:
                if 'Y' in item:
                    son.append(item)
                else:
                    daughter.append(item)
            string += 'SON\n'
            for item in son:
                string += didic[item] + '     ' + str(self.baby[item] * 50) + '%' + '\n'
            string += '\n\nDAUGHTER\n'
            for item in daughter:
                string += didic[item] + '     ' + str(self.baby[item] * 50) + '%' + '\n'
            return string
        else:
            for item in self.baby:
                string += didic[item] + '     ' + str(self.baby[item] * 25) + '%' + '\n'
        string += '\n\n***it only probability***'
        return string

    def back(self):
        self.name = ''
        app = Home(self.root)
            
root = tk.Tk()
app = Home(root)
root.mainloop()
