import torch
import torch.nn as nn
import torch.nn.functional as F
from metrics_torch.ERGAS_TORCH import ergas_torch
from metrics_torch.Q2N_TORCH import q2n_torch
from metrics_torch.SAM_TORCH import sam_torch
try:
    import lightning as L
except:
    import pytorch_lightning as L




##############################################################################################################
class Resblock(nn.Module):
    def __init__(self):
        super(Resblock, self).__init__()

        channel = 32
        self.conv20 = nn.Conv2d(in_channels=channel, out_channels=channel, kernel_size=3, stride=1, padding=1)
        self.conv21 = nn.Conv2d(in_channels=channel, out_channels=channel, kernel_size=3, stride=1, padding=1)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):  # x= hp of ms; y = hp of pan
        rs1 = self.relu(self.conv20(x))  # Bsx32x64x64
        rs1 = self.conv21(rs1)  # Bsx32x64x64
        rs = torch.add(x, rs1)  # Bsx32x64x64
        return rs
##############################################################################################################

class PanNet(L.LightningModule):
    def __init__(self, spectral_num, channel=32, reg=True):
        super(PanNet, self).__init__()
        self.reg = reg

        # ConvTranspose2d: output = (input - 1)*stride + outpading - 2*padding + kernelsize
        self.deconv = nn.ConvTranspose2d(in_channels=spectral_num,  out_channels=spectral_num,  kernel_size=8, stride=4, padding=2)
        self.conv1 = nn.Conv2d(in_channels=spectral_num + 1,        out_channels=channel,       kernel_size=3, stride=1, padding=1)  
        self.res1 = Resblock()
        self.res2 = Resblock()
        self.res3 = Resblock()
        self.res4 = Resblock()
        self.conv3 = nn.Conv2d(in_channels=channel,                 out_channels=spectral_num,  kernel_size=3, stride=1, padding=1)
        self.relu = nn.ReLU(inplace=True)

        self.backbone = nn.Sequential(  # method 2: 4 resnet repeated blocks
            self.res1,
            self.res2,
            self.res3,
            self.res4
        )


    def forward(self, input):# x= hp of ms; y = hp of pan
        pan = input["pan"]
        ms = input["ms"]
        lms = input["lms"]
        
        output_deconv = self.deconv(ms)
        input = torch.cat([output_deconv, pan], 1)  # Bsx9x64x64
        rs = self.relu(self.conv1(input))  # Bsx32x64x64
        rs = self.backbone(rs)  # ResNet's backbone!
        rs = self.conv3(rs) # Bsx8x64x64
        output = torch.add(rs, lms)

        return output
    
    def configure_optimizers(self):
        torch.optim.Adam(self.parameters(), lr=1e-3)

    def training_step(self, batch, batch_idx):
        y_hat = self(batch)

        y = batch['gt']
        loss = torch.nn.functional.mse_loss(y_hat, y)
        with torch.no_grad():
            ergas = ergas_torch(y_hat, y) 
            sam = sam_torch(y_hat, y)
            self.log_dict({'training_loss': loss, 
                        'training_sam':   sam, 
                        'training_ergas': ergas}, 
                            prog_bar=True)
        return loss
    
    def validation_step(self, batch, batch_idx):
        y_hat = self(batch)

        y = batch['gt']
        loss = torch.nn.functional.mse_loss(y_hat, y)
        with torch.no_grad():
            ergas = ergas_torch(y_hat, y)  
            sam = sam_torch(y_hat, y)
            self.log_dict({'validation_loss':  loss, 
                        'validation_sam':   sam, 
                        'validation_ergas': ergas}, 
                            prog_bar=True)
        return loss
    
    def test_step(self, batch, batch_idx):
        y_hat = self(batch)

        y = batch['gt']

        with torch.no_grad():
            sam = sam_torch(y_hat, y)
            ergas = ergas_torch(y_hat, y)
            q2n = q2n_torch(y_hat, y)
            
            self.log_dict({#'test_loss':  loss, 
                        'test_sam':   sam, 
                        'test_ergas': ergas,
                        'test_q2n': q2n}, 
                            prog_bar=True)

    def predict_step(self, batch, batch_idx):
        x = batch
        preds = self(x)
        return preds
    