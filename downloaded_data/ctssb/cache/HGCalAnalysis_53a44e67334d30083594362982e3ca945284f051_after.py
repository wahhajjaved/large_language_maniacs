"""Analysis helper tools for HGCal ntuples on EOS."""
import ROOT
import os
import math
import logging


class NullHandler(logging.Handler):
    """NullHandler for logging module."""

    def emit(self, record):
        """emit."""
        pass

logging.getLogger(__name__).addHandler(NullHandler())


def createOutputDir(outDir):
    if not os.path.exists(outDir):
        os.makedirs(outDir)


def saveHistograms(histDict, canvas, outDir, imgType, logScale=False):
    logString = ""
    if logScale:
        canvas.SetLogy(True)
        logString = "_log"
    else:
        canvas.SetLogy(False)
    for key, item in histDict.items():
        # do not save empty histograms
        if (type(item) == ROOT.TH1F) or (type(item) == ROOT.TH2F):
            if item.GetEntries() == 0:
                continue
        if type(item) == ROOT.TH2F:
            item.Draw("colz")
        else:
            item.Draw()
            if key.find("delta") >= 0 and key.find("delta_R") < 0 and key.find("deltaover") < 0:
                ROOT.gStyle.SetOptFit(1)
                item.Fit("gaus")
        canvas.SaveAs("{}/{}{}.{}".format(outDir, key, logString, imgType))
        if type(item) == ROOT.TH2F:
            pX = item.ProjectionX("pX")
            pX.Draw()
            canvas.SaveAs("{}/{}{}_projectionX.{}".format(outDir, key, logString, imgType))
            pX.Delete()
            pY = item.ProjectionY("pY")
            pY.Draw()
            canvas.SaveAs("{}/{}{}_projectionY.{}".format(outDir, key, logString, imgType))
            pY.Delete()
            pfX = item.ProfileX("pfX")
            pfX.Draw()
            canvas.SaveAs("{}/{}{}_profileX.{}".format(outDir, key, logString, imgType))
            pfX.Delete()
            pfY = item.ProfileY("pfY")
            pfY.Draw()
            canvas.SaveAs("{}/{}{}_profileY.{}".format(outDir, key, logString, imgType))
            pfY.Delete()



def getGenParticles(event, histDict, dvzCut):

    vGenParticleTLV = []
    for particle in event.particles:
        nonConverted = False
        if abs(particle.dvz) > dvzCut:
            nonConverted = True
            logging.debug("gen particle: {}, {}, {}".format(particle.pt, particle.eta, particle.phi))
        if not nonConverted:
            logging.debug("converted photon: {}".format(particle.dvz))
            continue
        if (abs(particle.eta) < 1.6) or (abs(particle.eta) > 2.8):
            logging.debug("photon outside detector coverage, eta: {}".format(particle.eta))
            continue
        if histDict.has_key("GenPart_energy"):
            histDict["GenPart_energy"].Fill(particle.energy)
            histDict["GenPart_pt"].Fill(particle.pt)
            histDict["GenPart_eta"].Fill(particle.eta)
            histDict["GenPart_phi"].Fill(particle.phi)
            histDict["GenPart_dvz"].Fill(particle.dvz)
        particleTLV = ROOT.TLorentzVector()
        particleTLV.SetPtEtaPhiE(
            particle.pt, particle.eta, particle.phi, particle.energy)
        vGenParticleTLV.append(particleTLV)
    return vGenParticleTLV


def getMultiClusters(clusters, histDict, prefix, dRCut, energyCut, matchesGen):

    vMulticlusterTLV = []
    usedCluster = [False] * len(clusters)
    for j, simCl1 in enumerate((clusters)):
        logging.debug(usedCluster)
        logging.debug("j: {} {} {} {}".format(j, simCl1.pt, simCl1.eta, simCl1.phi))
        if (simCl1.energy < energyCut) or (usedCluster[j]) or not matchesGen[j]:
            logging.debug("skip")
            continue
        histDict["%s_energy" %prefix].Fill(simCl1.energy)
        histDict["%s_pt" %prefix].Fill(simCl1.pt)
        histDict["%s_eta" %prefix].Fill(simCl1.eta)
        histDict["%s_phi" %prefix].Fill(simCl1.phi)
        if (prefix == "SimClus"):
            for i,layer in enumerate(simCl1.layers):
                histDict["%s_layers_energy" %prefix].Fill(layer, simCl1.energy*simCl1.fractions[i])
                histDict["%s_cells_energy" %prefix].Fill(simCl1.cells[i], simCl1.energy*simCl1.fractions[i])
                histDict["%s_wafers_energy" %prefix].Fill(simCl1.wafers[i], simCl1.energy*simCl1.fractions[i])
                histDict["%s_fractions_energy" %prefix].Fill(simCl1.fractions[i], simCl1.energy*simCl1.fractions[i])
                histDict["%s_layers_pt" %prefix].Fill(layer, simCl1.pt*simCl1.fractions[i])
                histDict["%s_cells_pt" %prefix].Fill(simCl1.cells[i], simCl1.pt*simCl1.fractions[i])
                histDict["%s_wafers_pt" %prefix].Fill(simCl1.wafers[i], simCl1.pt*simCl1.fractions[i])
                histDict["%s_fractions_pt" %prefix].Fill(simCl1.fractions[i], simCl1.pt*simCl1.fractions[i])
                histDict["%s_layers_fractions" %prefix].Fill(layer, simCl1.fractions[i])
                histDict["%s_cells_fractions" %prefix].Fill(simCl1.cells[i], simCl1.fractions[i])
                histDict["%s_wafers_fractions" %prefix].Fill(simCl1.wafers[i], simCl1.fractions[i])
        usedCluster[j] = True
        multiclusterTLV = ROOT.TLorentzVector()
        multiclusterTLV.SetPtEtaPhiE(
            simCl1.pt, simCl1.eta, simCl1.phi, simCl1.energy)

        # for k, simCl2 in enumerate((clusters)[j + 1:]):
        #     l = j+k+1
        #     logging.debug("l: {} {} {} {}".format(l, simCl2.pt, simCl2.eta, simCl2.phi, clusters[l].pt))
        #     if (simCl2.energy < energyCut):
        #         logging.debug("skip")
        #         continue
        #     if not (usedCluster[l]) and matchesGen[j]:
        #         dR = deltaR(simCl1, simCl2)
        #         logging.debug("unused, DeltaR = {}".format(dR))
        #         if (dR < dRCut):
        #             histDict["%s_energy" %prefix].Fill(simCl1.energy)
        #             histDict["%s_pt" %prefix].Fill(simCl1.pt)
        #             histDict["%s_eta" %prefix].Fill(simCl1.eta)
        #             histDict["%s_phi" %prefix].Fill(simCl1.phi)
        #             if (prefix == "SimClus"):
        #                 histDict["%s_simEnergy" %prefix].Fill(simCl1.simEnergy)
        #                 for i,layer in enumerate(simCl1.layers):
        #                     histDict["%s_layers_energy" %prefix].Fill(layer, simCl1.energy*simCl1.fractions[i])
        #                     histDict["%s_cells_energy" %prefix].Fill(simCl1.cells[i], simCl1.energy*simCl1.fractions[i])
        #                     histDict["%s_wafers_energy" %prefix].Fill(simCl1.wafers[i], simCl1.energy*simCl1.fractions[i])
        #                     histDict["%s_fractions_energy" %prefix].Fill(simCl1.fractions[i], simCl1.energy*simCl1.fractions[i])
        #                     histDict["%s_layers_pt" %prefix].Fill(layer, simCl1.pt*simCl1.fractions[i])
        #                     histDict["%s_cells_pt" %prefix].Fill(simCl1.cells[i], simCl1.pt*simCl1.fractions[i])
        #                     histDict["%s_wafers_pt" %prefix].Fill(simCl1.wafers[i], simCl1.pt*simCl1.fractions[i])
        #                     histDict["%s_fractions_pt" %prefix].Fill(simCl1.fractions[i], simCl1.pt*simCl1.fractions[i])
        #                     histDict["%s_layers_fractions" %prefix].Fill(layer, simCl1.fractions[i])
        #                     histDict["%s_cells_fractions" %prefix].Fill(simCl1.cells[i], simCl1.fractions[i])
        #                     histDict["%s_wafers_fractions" %prefix].Fill(simCl1.wafers[i], simCl1.fractions[i])
        #             histDict["%s_dRtoSeed" %prefix].Fill(dR)
        #             logging.debug("pass cut")
        #             usedCluster[l] = True
        #             tmpTLV = ROOT.TLorentzVector()
        #             tmpTLV.SetPtEtaPhiE(
        #                 simCl2.pt, simCl2.eta, simCl2.phi, simCl2.energy)
        #             multiclusterTLV += tmpTLV
        vMulticlusterTLV.append(multiclusterTLV)
        histDict["multi%s_energy"%prefix].Fill(multiclusterTLV.E())
        histDict["multi%s_pt"%prefix].Fill(multiclusterTLV.Pt())
        histDict["multi%s_eta"%prefix].Fill(multiclusterTLV.Eta())
        histDict["multi%s_phi"%prefix].Fill(multiclusterTLV.Phi())
        logging.debug("multicluster: {} {} {}".format(multiclusterTLV.Pt(), multiclusterTLV.Eta(), multiclusterTLV.Phi()))

    logging.debug("end of loop: {}".format(usedCluster))
    vMulticlusterTLV = sorted(
        vMulticlusterTLV, key=lambda tlv: tlv.Pt(), reverse=True)
    return vMulticlusterTLV

def selectMatchingClusters(refCollection, selCollection, dRcut, histDict, comp):

    selectedClusters = []
    matchedCluster = [False]*len(refCollection)
    for sel in selCollection:
        for i,ref in enumerate(refCollection):
            if sel.DeltaR(ref) < dRcut:
                selectedClusters.append(sel)
                histDict["multi%s_delta_energy" %comp].Fill(ref.E()-sel.E())
                histDict["multi%s_delta_pt" %comp].Fill(ref.Pt()-sel.Pt())
                histDict["multi%s_deltaover_energy" %comp].Fill((ref.E()-sel.E())/ref.E())
                histDict["multi%s_deltaover_pt" %comp].Fill((ref.Pt()-sel.Pt())/ref.Pt())
                histDict["multi%s_delta_eta" %comp].Fill(ref.Eta()-sel.Eta())
                histDict["multi%s_delta_phi" %comp].Fill(ref.Phi()-sel.Phi())
                histDict["multi%s_delta_R" %comp].Fill(ref.DeltaR(sel))
                matchedCluster[i] = True
    for match in matchedCluster:
        if match:
            histDict["multi%s_eff" %comp].Fill(1)
        else:
            histDict["multi%s_eff" %comp].Fill(0)

    return selectedClusters


def deltaR(p1, p2):
    dphi = p1.phi - p2.phi
    deta = p1.eta - p2.eta
    dR = math.sqrt(dphi * dphi + deta * deta)
    return dR

def deltaR2(tlv1, p2):
    dphi = tlv1.Phi() - p2.phi
    deta = tlv1.Eta() - p2.eta
    dR = math.sqrt(dphi * dphi + deta * deta)
    return dR



def main():

        c = ROOT.TCanvas(particleType, particleType, 500, 500)


        for dRCut in dRCuts:

            outDir = ("simClusVsPFCand_dR%4.3f" % dRCut).replace(".","_")
            logging.info(outDir)

            # create output dir
            createOutputDir(outDir)
            if not os.path.exists(outDir+"/"+particleType):
                os.makedirs(outDir+"/"+particleType)

            histDict = {}
            clusters = ["SimClus", "PFClus", "GenPart"]
            for clus in clusters:

                histDict["%s_energy" %clus] = ROOT.TH1F("%s_energy" %clus, "%s_energy;E [GeV]" %clus, 200, 0, 50)
                histDict["%s_pt" %clus] = ROOT.TH1F("%s_pt" %clus, "%s_pt;p_{T} [GeV]" %clus, 100, 0, 10)
                histDict["%s_eta" %clus] = ROOT.TH1F("%s_eta" %clus, "%s_eta;#eta" %clus, 100, -5, 5)
                histDict["%s_phi" %clus] = ROOT.TH1F("%s_phi" %clus, "%s_phi;#phi" %clus, 100, -3.2, 3.2)
                if (clus == "SimClus"):
                    histDict["%s_simEnergy" %clus] = ROOT.TH1F("%s_simEnergy" %clus, "%s_simEnergy;simE [GeV]" %clus, 200, 0, 50)
                    histDict["%s_layers_energy" %clus] = ROOT.TH2F("%s_layers_energy" %clus, "%s_layers_energy;layers;energy [GeV]" %clus, 30, 0, 30, 200, 0, 50)
                    histDict["%s_cells_energy" %clus] = ROOT.TH2F("%s_cells_energy" %clus, "%s_cells_energy;cells;energy [GeV]" %clus, 245, 0, 245, 200, 0, 50)
                    histDict["%s_wafers_energy" %clus] = ROOT.TH2F("%s_wafers_energy" %clus, "%s_wafers_energy;wafer;energy [GeV]" %clus, 550, 0, 550, 200, 0, 50)
                    histDict["%s_fractions_energy" %clus] = ROOT.TH2F("%s_fractions_energy" %clus, "%s_fractions_energy;fraction;energy [GeV]" %clus, 100, 0, 1, 200, 0, 50)
                    histDict["%s_layers_pt" %clus] = ROOT.TH2F("%s_layers_pt" %clus, "%s_layers_pt;layers;p_{T} [GeV]" %clus, 30, 0, 30, 200, 0, 50)
                    histDict["%s_cells_pt" %clus] = ROOT.TH2F("%s_cells_pt" %clus, "%s_cells_pt;cells;p_{T} [GeV]" %clus, 245, 0, 245, 200, 0, 50)
                    histDict["%s_wafers_pt" %clus] = ROOT.TH2F("%s_wafers_pt" %clus, "%s_wafers_pt;wafer;p_{T} [GeV]" %clus, 550, 0, 550, 200, 0, 50)
                    histDict["%s_fractions_pt" %clus] = ROOT.TH2F("%s_fractions_pt" %clus, "%s_fractions_pt;fraction;p_{T} [GeV]" %clus, 100, 0, 1, 200, 0, 50)
                    histDict["%s_layers_fractions" %clus] = ROOT.TH2F("%s_layers_fractions" %clus, "%s_layers_fractions;layers;fractions" %clus, 30, 0, 30, 100, 0, 1)
                    histDict["%s_cells_fractions" %clus] = ROOT.TH2F("%s_cells_fractions" %clus, "%s_cells_fractions;cells;fractions" %clus, 245, 0, 245, 100, 0, 1)
                    histDict["%s_wafers_fractions" %clus] = ROOT.TH2F("%s_wafers_fractions" %clus, "%s_wafers_fractions;wafer;fractions" %clus, 550, 0, 550, 100, 0, 1)
                histDict["%s_dRtoSeed" %clus] = ROOT.TH1F(
                    "%s_dRtoSeed" %clus, "%s_dRtoSeed;#Delta R to seed" %clus, 100, -0.2, 0.2)

                if (clus != "GenPart"):
                    histDict["multi%s_energy" %clus] = ROOT.TH1F("multi%s_energy" %clus, "multi%s_energy;E [GeV]" %clus, 200, 0, 50)
                    histDict["multi%s_pt" %clus] = ROOT.TH1F("multi%s_pt" %clus, "multi%s_pt;p_{T} [GeV]" %clus, 100, 0, 10)
                    histDict["multi%s_eta" %clus] = ROOT.TH1F("multi%s_eta" %clus, "multi%s_eta;#eta" %clus, 100, -5, 5)
                    histDict["multi%s_phi" %clus] = ROOT.TH1F("multi%s_phi" %clus, "multi%s_phi;#phi" %clus, 100, -3.2, 3.2)

            compClusters = ["SimVsPF", "GenVsPF", "GenVsSim"]
            for comp in compClusters:
                if comp.find("Gen") < 0:
                    histDict["%s_delta_energy" %comp] = ROOT.TH1F("%s_delta_energy" %comp, "%s_delta_energy;#Delta E [GeV]" %comp, 100, -10, 10)
                    histDict["%s_delta_pt" %comp] = ROOT.TH1F("%s_delta_pt" %comp, "%s_delta_pt;#Delta p_{T} [GeV]" %comp, 100, -5, 5)
                    histDict["%s_deltaover_energy" %comp] = ROOT.TH1F("%s_deltaover_energy" %comp, "%s_delta_overenergy;#Delta E/E" %comp, 100, -1, 1)
                    histDict["%s_deltaover_pt" %comp] = ROOT.TH1F("%s_deltaover_pt" %comp, "%s_deltaover_pt;#Delta p_{T}/p_{T}" %comp, 100, -1, 1)
                    histDict["%s_delta_eta" %comp] = ROOT.TH1F("%s_delta_eta" %comp, "%s_delta_eta;#Delta #eta" %comp, 100, -1, 1)
                    histDict["%s_delta_phi" %comp] = ROOT.TH1F("%s_delta_phi" %comp, "%s_delta_phi;#Delta #phi" %comp, 100, -1, 1)
                    histDict["%s_delta_R" %comp] = ROOT.TH1F("%s_delta_R" %comp, "%s_delta_R;#Delta R" %comp, 100, -1, 1)

                histDict["multi%s_delta_energy" %comp] = ROOT.TH1F("multi%s_delta_energy" %comp, "multi%s_delta_energy;#Delta E [GeV]" %comp, 100, -10, 10)
                histDict["multi%s_delta_pt" %comp] = ROOT.TH1F("multi%s_delta_pt" %comp, "multi%s_delta_pt;#Delta p_{T} [GeV]" %comp, 100, -5, 5)
                histDict["multi%s_deltaover_energy" %comp] = ROOT.TH1F("multi%s_deltaover_energy" %comp, "multi%s_deltaover_energy;#Delta E/E" %comp, 100, -5, 5)
                histDict["multi%s_deltaover_pt" %comp] = ROOT.TH1F("multi%s_deltaover_pt" %comp, "multi%s_deltaover_pt;#Delta p_{T}/p_{T}" %comp, 100, -5, 5)
                histDict["multi%s_delta_eta" %comp] = ROOT.TH1F("multi%s_delta_eta" %comp, "multi%s_delta_eta;#Delta #eta" %comp, 100, -1, 1)
                histDict["multi%s_delta_phi" %comp] = ROOT.TH1F("multi%s_delta_phi" %comp, "multi%s_delta_phi;#Delta #phi" %comp, 100, -1, 1)
                histDict["multi%s_delta_R" %comp] = ROOT.TH1F("multi%s_delta_R" %comp, "multi%s_delta_R;#Delta R" %comp, 100, -1, 1)
                histDict["multi%s_eff" %comp] = ROOT.TH1F("multi%s_eff" %comp, "multi%s_eff;eff." %comp, 2, -0.5, 1.5)

                if comp.find("Gen") < 0:
                    histDict["multi%s_selected_delta_energy" %comp] = ROOT.TH1F("multi%s_selected_delta_energy" %comp, "multi%s_selected_delta_energy;#Delta E [GeV]" %comp, 100, -10, 10)
                    histDict["multi%s_selected_delta_pt" %comp] = ROOT.TH1F("multi%s_selected_delta_pt" %comp, "multi%s_selected_delta_pt;#Delta p_{T} [GeV]" %comp, 100, -5, 5)
                    histDict["multi%s_selected_deltaover_energy" %comp] = ROOT.TH1F("multi%s_selected_deltaover_energy" %comp, "multi%s_selected_deltaover_energy;#Delta E/E" %comp, 100, -10, 10)
                    histDict["multi%s_selected_deltaover_pt" %comp] = ROOT.TH1F("multi%s_selected_deltaover_pt" %comp, "multi%s_selected_deltaover_pt;#Delta p_{T}/p_{T}" %comp, 100, -5, 5)
                    histDict["multi%s_selected_delta_eta" %comp] = ROOT.TH1F("multi%s_selected_delta_eta" %comp, "multi%s_selected_delta_eta;#Delta #eta" %comp, 100, -1, 1)
                    histDict["multi%s_selected_delta_phi" %comp] = ROOT.TH1F("multi%s_selected_delta_phi" %comp, "multi%s_selected_delta_phi;#Delta #phi" %comp, 100, -1, 1)
                    histDict["multi%s_selected_delta_R" %comp] = ROOT.TH1F("multi%s_selected_delta_R" %comp, "multi%s_selected_delta_R;#Delta R" %comp, 100, -1, 1)
                    histDict["multi%s_selected_eff" %comp] = ROOT.TH1F("multi%s_selected_eff" %comp, "multi%s_selected_eff;eff." %comp, 2, -0.5, 1.5)


            # dRCut = 0.015
            loose_dRCut = 0.1
            energyCut = 0 #0.3

            dvzCut = 320
            nEvents = chain.GetEntries()

            for i, event in enumerate(chain):
                if (i%100 == 0):
                    logging.info("Event {} of {}".format(i, nEvents))
                logging.debug("="*20 + "\nEvent: {}".format(i))

                vGenParticleTLV = getGenParticles(event, histDict, dvzCut)
                if len(vGenParticleTLV) == 0:
                    continue

                matchesGen = [False]*len(event.simcluster)
                count = 0
                for simCl, pfCl in zip(event.simcluster, event.pfcluster):
                    # logging.info("{} {}".format(simCl.pt, pfCl.pt))
                    for j, genPart in enumerate(vGenParticleTLV):
                        # if deltaR2(genPart, simCl) < loose_dRCut:
                        if genPart.Eta()*simCl.eta  > 0:
                            matchesGen[count] = True
                            histDict["SimVsPF_delta_energy"].Fill(simCl.energy-pfCl.energy)
                            histDict["SimVsPF_delta_pt"].Fill(simCl.pt-pfCl.pt)
                            histDict["SimVsPF_deltaover_energy"].Fill((simCl.energy-pfCl.energy)/simCl.energy)
                            histDict["SimVsPF_deltaover_pt"].Fill((simCl.pt-pfCl.pt)/simCl.pt)
                            histDict["SimVsPF_delta_eta"].Fill(simCl.eta-pfCl.eta)
                            histDict["SimVsPF_delta_phi"].Fill(simCl.phi-pfCl.phi)
                            histDict["SimVsPF_delta_R"].Fill(deltaR(simCl, pfCl))
                            break
                    count += 1

                vMultiSimClusterTLV = getMultiClusters(event.simcluster, histDict, "SimClus", dRCut, energyCut, matchesGen)
                vMultiPFClusterTLV = getMultiClusters(event.pfcluster, histDict, "PFClus", dRCut, energyCut, matchesGen)

                matchedMultiPFClusterTLV = selectMatchingClusters(vMultiSimClusterTLV, vMultiPFClusterTLV, loose_dRCut, histDict, "SimVsPF")
                selectedMultiSimClusterTLV = selectMatchingClusters(vGenParticleTLV, vMultiSimClusterTLV, loose_dRCut, histDict, "GenVsSim")
                selectedMultiPFClusterTLV = selectMatchingClusters(vGenParticleTLV, vMultiPFClusterTLV, loose_dRCut, histDict, "GenVsPF")

                matchedAndSelectedMultiPFClusterTLV = selectMatchingClusters(selectedMultiSimClusterTLV, selectedMultiPFClusterTLV, loose_dRCut, histDict, "SimVsPF_selected")

                # if i > 0:
                #     break

            saveHistograms(histDict, c, outDir, imgType)

        chain.Clear()

if __name__ == '__main__':
    main()
