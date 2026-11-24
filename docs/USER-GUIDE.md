# Home Dashboard: user guide

The dashboard is a Raspberry Pi 3B that boots straight into a full-screen family
dashboard: photos, clock, news, weather and prayer times. You change everything from
a settings website on your home network. There is no desktop, browser or login on
the Pi itself.

## 1. Put the system on an SD card

You need a microSD card of 8 GB or more, and the file `dashboard-<version>.img.xz`
from the [releases page](https://github.com/DaniyalAqeela/home-dashboard/releases).

1. Install **Raspberry Pi Imager** from raspberrypi.com/software.
2. **Choose Device**: Raspberry Pi 3. **Choose OS**: scroll to the bottom and pick
   **Use custom**, then select the `.img.xz` file. **Choose Storage**: your SD card.
3. If Imager offers "OS customisation", choose **No**. The dashboard doesn't use it.
4. Write the card and put it in the Pi.

## 2. First start

1. Plug the Pi into the TV or monitor with HDMI, and into your router with an
   **Ethernet cable**.
2. Plug in the power. The first start takes about a minute: the card's free space
   is set up for photos.
3. The screen shows **Welcome to your dashboard** and an address.

## 3. Open the settings website

On a phone or computer on the same network, open **http://dashboard.local**.
If that doesn't open (some Android phones and older Windows PCs can't use `.local`
names), type the number address shown on the dashboard screen, for example
`http://192.168.1.23`.

The first visit asks you to **create a password**. It protects the settings. Anyone
on your network can open the page, but only someone with the password can change
anything.

## 4. Family photos from Google Drive

1. In Google Drive, right-click the photo folder and choose **Share → Share**.
2. Under **General access**, change "Restricted" to **Anyone with the link**
   (Viewer). Click **Copy link**, then **Done**.
3. In the settings website, go to **Photos**, paste the link into
   **Google Drive folder link** and wait a moment. The first sync downloads every
   photo, which can take a while for a large folder. The status line shows the
   progress.

New photos you add to the folder appear within the sync interval (30 minutes by
default), or straight away with **Sync now**. Deleted photos are removed too.

**Not all photos appear?** Without an API key the dashboard can only see the first
50 or so photos in a folder. For bigger folders, create a free Google API key (Google
Cloud Console → APIs & Services → enable the **Google Drive API** → Credentials →
Create credentials → API key), then paste it into **Google API key**.

You can also **upload photos** from your phone or computer on the same page. They
are shown together with the Drive photos.

## 5. Wi-Fi

Ethernet works without setup. To move to Wi-Fi:

1. **Location**: set your place first. It also sets the Wi-Fi country.
2. **Network → Scan for networks**, tap your network, type the password and press
   **Connect**.
3. Check that the status says "Wi-Fi: connected", then unplug the cable. The
   address `http://dashboard.local` stays the same. A number address will change.

When a cable is plugged in, Ethernet is always used first.

## 6. Location: weather, prayer times and the clock

**Location**: search for your town and pick it from the list. That sets the
coordinates (for weather and prayer times), the time zone (for the clock) and the
Wi-Fi country.

The prayer-time calculation method, the Asr school and per-prayer minute
adjustments are options of the **Shalat times** widget (see Design).

## 7. Design the screen

The **Design** tab shows a live picture of the real screen, updated every second.

- **Click** a widget to select it. Its settings open on the right.
- **Drag** it to move it. **Drag the round corner handle** to resize it.
- **Add widget** (when nothing is selected) adds another clock, news list, photo
  frame and so on. You can have as many as you like.
- **Duplicate / To front / To back / Delete** act on the selected widget.
- **Style** sets each widget's background (with opacity), corner radius, padding,
  font, text size, colour, alignment and text shadow.
- With nothing selected, **Theme** sets the screen background and the default
  font and colour.

The **Display** tab has:

- **Rotation**, for a portrait-mounted screen.
- **Resolution**: "Automatic" is best for almost every TV.
- **UI scale**, to make everything bigger or smaller.
- **Edge padding**, for TVs that cut off the picture edges.
- **Screen off at night**: set the off and on times.

## 8. Updates

**Updates → Check for updates** looks for a newer release on GitHub. If there is
one, press **Install**. You can also **Upload update file…** with a
`dashboard-app-<version>.tar.gz` file.

The dashboard restarts with the new version. If the new version fails to start three
times in a row, it goes back to the previous version automatically. You can also
press **Go back to <version>** yourself.

Updates replace only the dashboard software. Your settings and photos are kept.

## 9. Backup

**System → Download backup** saves your design, settings and uploaded photos into
one file. Make one before you rewrite the SD card. Afterwards, use
**Restore from backup…**. Drive photos aren't in the backup: they download again
by themselves. The password isn't in the backup either: you create a new one.

## 10. Forgot the password?

1. Unplug the Pi and put the SD card in a computer. A drive called **boot**
   appears.
2. Create an empty file called `reset-password` on it (no `.txt` at the end).
3. Put the card back and start the Pi. The settings website asks you to create a
   new password. Your design and photos are kept.

## 11. Troubleshooting

| What you see | What to do |
|---|---|
| "Clock not set yet" at the top | The dashboard has no internet. Check the cable or Wi-Fi. The clock sets itself once it is online. |
| "This folder isn't shared publicly" | Do step 4.2 again: General access must be "Anyone with the link". |
| `dashboard.local` doesn't open | Use the number address instead. Your router's list of connected devices shows it under the name "dashboard". Once you're in, **System → About** shows it too. |
| Screen is black at night | That's the night schedule (Display → Screen off). |
| Wi-Fi password was wrong and the Pi is now unreachable | Plug in an Ethernet cable. It always works. |
| Something else | **System → Show recent logs** shows what the dashboard has been doing. **Restart dashboard** fixes most hiccups; **Reboot** restarts the whole Pi. |

Leave the Pi plugged in. It is built to run 24/7, and the system part of the card is
read-only, so a power cut won't damage it.
