from ROOT import *
import random 
from array import array
import itertools

def compute_eff():
    #njet histo
    h_njet = TH1D("h_njet", "h_njet", 5, 0.5, 5.5)
    h_njet.Fill(1, 5)
    h_njet.Fill(2, 4)
    h_njet.Fill(3, 3)
    h_njet.Fill(4, 2)
    h_njet.Fill(5, 1)

    #x histo
    h_x = TH1D("h_x", "h_x", 5, 0, 10)
    h_x.Fill(1, 1)
    h_x.Fill(2, 2)
    h_x.Fill(3, 3)
    h_x.Fill(4, 2)
    h_x.Fill(5, 4)

    #eff(x) histo
    h_eff_true = TH1D("h_eff_true", "h_eff_true", 5, 0, 10);#could be different binning
    h_eff_true.Fill(1, 0.1)
    h_eff_true.Fill(2, 0.2)
    h_eff_true.Fill(3, 0.2)
    h_eff_true.Fill(4, 0.2)
    h_eff_true.Fill(5, 0.3)

    #histograms filled by the toys
    h_x_gen    = TH1D("h_x_gen",    "h_x_gen",    5, 0,   10)
    h_njet_gen = TH1D("h_njet_gen", "h_njet_gen", 5, 0.5, 5.5)
    h_bkg_est  = TH1D("h_bkg_est",  "h_bkg_est",  6, -0.5, 5.5)
    h_bkg_act  = TH1D("h_bkg_act",  "h_bkg_act",  6, -0.5, 5.5)
    h_bin  = TH1D("h_bin",  "h_bin",  20, 0, 3)


    #loop over events
    for e in range(10000):

        ntags = 0
        vect_prob = []

        #sample njet 
        njet = h_njet.GetRandom()
        njet_int = int(njet+0.5)
        h_njet_gen.Fill(njet_int)

        for j in range(njet_int):

            #sample x
            x = h_x.GetRandom()
            h_x_gen.Fill(x)
                       
            prob = h_eff_true.GetBinContent(h_eff_true.FindBin(x))
            vect_prob.append(prob)
           
            #using h_eff_true, not from toys!
            r = random.random()
            if(r<prob):
                ntags+=1

        h_bkg_act.Fill(ntags)

        #compute probabilities from x values
        binomial_sum = 0
        for k in range(0,6):
            binomial_term = binomialTerm(vect_prob,k)
            binomial_sum += binomial_term
            h_bkg_est.Fill(k,binomial_term)
        h_bin.Fill(binomial_sum)

    c_bkg = TCanvas("c_bkg", "c_bkg", 640, 480)
    h_bkg_act.Draw("HIST E")
    h_bkg_est.SetLineColor(2)
    h_bkg_est.Draw("HIST E SAMES")

    c_njet = TCanvas("c_njet", "c_njet", 640, 480)
    h_njet.DrawNormalized("HIST E")
    h_njet_gen.SetLineColor(2)
    h_njet_gen.DrawNormalized("HIST E SAMES")

    c_x = TCanvas("c_x", "c_x", 640, 480)
    h_x.DrawNormalized("HIST E")
    h_x_gen.SetLineColor(2)
    h_x_gen.DrawNormalized("HIST E SAMES")

    fout = TFile.Open("toy.root","RECREATE");
    h_bkg_act.Write()
    h_bkg_est.Write()
    h_eff_true.Write()
    h_njet.Write()
    h_njet_gen.Write()
    h_x.Write()
    h_x_gen.Write()
    h_bin.Write()
    c_x.Write()
    c_bkg.Write()
    c_njet.Write()


def binomialTerm(probList,k):
    if len(probList) < k:
        return 0
  
    retval=0
    for combo in itertools.combinations(range(0,len(probList)),k):
        addTerm=1
        for i in range(0,len(probList)):
            if i in combo:
                addTerm*=probList[i]
            else:
                addTerm*=(1-probList[i])
        retval+=addTerm
    
    return retval


def main():

   compute_eff() 

if __name__ == '__main__': main()
