"""A small convolutional network that reads one camera frame and predicts the plate pose."""
import torch
from torch import nn


class PlateNet(nn.Module):
    """Input: BGR image in 0..1, shape (N, 3, 240, 320). Output: [dx, dy, yaw, presence logit]."""

    def __init__(self):
        super().__init__()

        def block(channels_in, channels_out):
            return nn.Sequential(nn.Conv2d(channels_in, channels_out, 3, 2, 1, bias=False),
                                 nn.BatchNorm2d(channels_out), nn.ReLU(inplace=True))
        # Two extra coordinate channels keep the position of the plate in the image.
        self.features = nn.Sequential(
            nn.Conv2d(5, 16, 5, 2, 2, bias=False), nn.BatchNorm2d(16), nn.ReLU(inplace=True),
            block(16, 32), block(32, 48), block(48, 64), block(64, 96))
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(96 * 8 * 10, 128), nn.ReLU(inplace=True),
                                  nn.Linear(128, 4))

    def forward(self, x):
        n, _, height, width = x.shape
        ys = torch.linspace(-1, 1, height, device=x.device).view(1, 1, height, 1).expand(n, 1, height, width)
        xs = torch.linspace(-1, 1, width, device=x.device).view(1, 1, 1, width).expand(n, 1, height, width)
        return self.head(self.features(torch.cat([x, xs, ys], dim=1)))
