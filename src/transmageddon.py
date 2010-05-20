# Transmageddon
# Copyright (C) 2009 Christian Schaller <uraeus@gnome.org>
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.



import sys
import os

os.environ["GST_DEBUG_DUMP_DOT_DIR"] = "/tmp"
os.putenv('GST_DEBUG_DUMP_DIR_DIR', '/tmp')
import which
import time
import transcoder_engine
import gobject; gobject.threads_init()
from urlparse import urlparse
import codecfinder
import about
import presets
import utils
import datetime
import discoverer
from gettext import gettext as _
import gettext

try:
   import pygtk
   pygtk.require("2.0")
   import glib
   import gtk
   import pygst
   pygst.require("0.10")
   import gst
   import gst.pbutils
except Exception, e:
   print "failed to import required modules"
   print e
   sys.exit(1)

major, minor, patch = gobject.pygobject_version
if (major == 2) and (minor < 18):
   print "You need version 2.18.0 or higher of pygobject for Transmageddon" 
   sys.exit(1)

TARGET_TYPE_URI_LIST = 80
dnd_list = [ ( 'text/uri-list', 0, TARGET_TYPE_URI_LIST ) ]

supported_containers = [
        "Ogg",
        "Matroska",
        "AVI",
        "MPEG TS",
        "MPEG PS",
        "FLV",
        "Quicktime",
        "MPEG4",
        "3GPP",
        "MXF",
        "ASF"
]

supported_audio_codecs = [
       "apass",
       "vorbis",
       "flac",
       "mp3",
       "aac",
       "ac3",
       "speex",
       "celt",
       "amrnb",
       "wma2"
]

supported_video_codecs = [
       "vpass",
       "theora",
       "dirac",
       "h264",
       "mpeg2",
       "mpeg4",
       "xvid",
       "h263p",
       "wmv2"
]

# Maps containers to the codecs they support.  The first two elements are
# "special" in that they are the default audio/video selections for that
# container.
supported_container_map = {
    'Ogg':        [ 'vorbis', 'theora', 'flac', 'speex', 'celt', 'dirac' ],
    'MXF':        [ 'mp3', 'h264', 'aac', 'ac3', 'mpeg2', 'mpeg4' ],
    'Matroska':   [ 'flac', 'dirac', 'aac', 'ac3', 'theora', 'mp3', 'h264',
    'mpeg4', 'mpeg2', 'xvid', 'vorbis', 'h263p' ],
    'AVI':        [ 'mp3', 'h264', 'dirac', 'ac3', 'mpeg2', 'mpeg4', 'xvid','wma2','wmv2' ],
    'Quicktime':  [ 'aac', 'h264', 'ac3', 'dirac', 'mp3', 'mpeg2', 'mpeg4' ],
    'MPEG4':      [ 'aac', 'h264', 'mp3', 'mpeg2', 'mpeg4' ],
    '3GPP':       [ 'aac', 'h264', 'mp3', 'mpeg2', 'mpeg4','amrnb','h263p' ],
    'MPEG PS':    [ 'mp3', 'mpeg2', 'ac3', 'h264', 'aac', 'mpeg4' ],
    'MPEG TS':    [ 'mp3', 'h264', 'ac3', 'mpeg2', 'aac', 'mpeg4', 'dirac' ],
    'FLV':        [ 'mp3', 'h264' ],
    'ASF':        [ 'wma2','wmv2','mp3']
}

class TransmageddonUI:
   """This class loads the GtkBuilder file of the UI"""
   def __init__(self):
       #Set up i18n
       gettext.bindtextdomain("transmageddon","../../share/locale")
       gettext.textdomain("transmageddon")

       self.builder = gtk.Builder()

       #Set the Glade file
       self.uifile = "transmageddon.ui"
       self.builder.add_from_file(self.uifile)
       self.builder.connect_signals(self) # Initialize User Interface

       #Define functionality of our button and main window
       self.TopWindow = self.builder.get_object("TopWindow")
       self.FileChooser = self.builder.get_object("FileChooser")
       self.videoinformation = self.builder.get_object("videoinformation")
       self.audioinformation = self.builder.get_object("audioinformation")
       self.videocodec = self.builder.get_object("videocodec")
       self.audiocodec = self.builder.get_object("audiocodec")
       self.CodecBox = self.builder.get_object("CodecBox")
       self.presetchoice = self.builder.get_object("presetchoice")
       self.containerchoice = self.builder.get_object("containerchoice")
       self.rotationchoice = self.builder.get_object("rotationchoice")
       self.codec_buttons = dict()
       for c in supported_audio_codecs:
           self.codec_buttons[c] = self.builder.get_object(c+"button")
           self.codec_buttons[c].connect("clicked",
                                         self.on_audiobutton_pressed, c)
       for c in supported_video_codecs:
           self.codec_buttons[c] = self.builder.get_object(c+"button")
           self.codec_buttons[c].connect("clicked",
                                         self.on_videobutton_pressed, c)

       self.transcodebutton = self.builder.get_object("transcodebutton")
       self.ProgressBar = self.builder.get_object("ProgressBar")
       self.cancelbutton = self.builder.get_object("cancelbutton")
       self.StatusBar = self.builder.get_object("StatusBar")

       self.TopWindow.connect("destroy", gtk.main_quit)
       
       def get_file_path_from_dnd_dropped_uri(self, uri):
           # get the path to file
           path = ""
           if uri.startswith('file:\\\\\\'): # windows
               path = uri[8:] # 8 is len('file:///')
           elif uri.startswith('file://'): # nautilus, rox
               path = uri[7:] # 7 is len('file://')
           elif uri.startswith('file:'): # xffm
               path = uri[5:] # 5 is len('file:')

           return path

       def on_drag_data_received(widget, context, x, y, selection, target_type, timestamp):
           if target_type == TARGET_TYPE_URI_LIST:
               uri = selection.data.strip('\r\n\x00')
               self.builder.get_object ("FileChooser").set_uri(uri)

       self.TopWindow.connect('drag_data_received', on_drag_data_received)
       self.TopWindow.drag_dest_set( gtk.DEST_DEFAULT_MOTION |
           gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, dnd_list, gtk.gdk.ACTION_COPY)

       self.start_time = False
       self.multipass = False
       self.passcounter = False
       
       # Set the Videos XDG UserDir as the default directory for the filechooser, 
       # also make sure directory exists
       if 'get_user_special_dir' in glib.__dict__:
           self.videodirectory = glib.get_user_special_dir(glib.USER_DIRECTORY_VIDEOS)
       else:
           print "XDG video directory not available"
           self.videodirectory = os.getenv('HOME')
       if self.videodirectory is None:
           print "XDG video directory not available"
           self.videodirectory = os.getenv('HOME')
       CheckDir = os.path.isdir(self.videodirectory)
       if CheckDir == (False):
           os.mkdir(self.videodirectory)
       self.FileChooser.set_current_folder(self.videodirectory)

       # Setting AppIcon
       FileExist = os.path.isfile("../../share/pixmaps/transmageddon.svg")
       if FileExist:
           self.TopWindow.set_icon_from_file("../../share/pixmaps/transmageddon.svg")

       else:
           try:
               self.TopWindow.set_icon_from_file("transmageddon.svg")
           except:
               print "failed to find appicon"

       # default all but top box to insensitive by default
       # self.containerchoice.set_sensitive(False)
       self.CodecBox.set_sensitive(False)
       self.transcodebutton.set_sensitive(False)
       self.cancelbutton.set_sensitive(False)
       self.presetchoice.set_sensitive(False)
       self.containerchoice.set_sensitive(False)
       self.rotationchoice.set_sensitive(False)
       self.codec_buttons["apass"].set_sensitive(False)
       self.codec_buttons["vpass"].set_sensitive(False)

       # set default values for various variables
       self.AudioCodec = "vorbis"
       self.VideoCodec = "theora"
       self.ProgressBar.set_text(_("Transcoding Progress"))
       self.container = False
       self.vsourcecaps = False
       self.asourcecaps = False
       self.videopasstoggle=False
       self.audiopasstoggle=False
       self.containertoggle=False # this toggle is used to not check for encoders with pbutils
       self.discover_done=False # lets us know that discover is finished
       self.missingtoggle=False

       self.p_duration = gst.CLOCK_TIME_NONE
       self.p_time = gst.FORMAT_TIME

       # Populate the Container format combobox
       self.lst = supported_containers
       for i in self.lst:
           self.containerchoice.append_text(i)

       # Populate the rotatation box
       self.rotationlist = [_("No rotation (default)"), _("Clockwise 90 degrees"), _("Rotate 180 degrees"), 
                           _("Counterclockwise 90 degrees"), _("Horizontal flip"),
                           _("Vertical flip"), _("Upper left diagonal flip"),
                           _("Upper right diagnonal flip") ]

       for y in self.rotationlist: 
           self.rotationchoice.append_text(y)

       self.rotationchoice.set_active(0)
       self.rotationvalue = int(0) 
      
       # Populate Device Presets combobox
       devicelist = []
       shortname = []
       preset_list = sorted(presets.get().items(),
                            key = (lambda x: x[1].make + x[1].model))
       for x, (name, device) in enumerate(preset_list):
           self.presetchoice.append_text(str(device))
           devicelist.append(str(device))
           shortname.append(str(name))

       #for (name, device) in (presets.get().items()):
       #    shortname.append(str(name))
       self.presetchoices = dict(zip(devicelist, shortname))
       self.presetchoice.prepend_text(_("No Presets"))

       self.waiting_for_signal="False"

   # Get all preset values
   def reverse_lookup(self,v):
       for k in codecfinder.codecmap:
           if codecfinder.codecmap[k] == v:
               return k

   def provide_presets(self,devicename): 
       devices = presets.get()
       device = devices[devicename]
       preset = device.presets["Normal"]
       if preset.container == "application/ogg":
           self.containerchoice.set_active(0)
       elif preset.container == "video/x-matroska":
           self.containerchoice.set_active(1)
       elif preset.container == "video/x-msvideo":
           self.containerchoice.set_active(2)
       elif preset.container == "video/mpegts":
           self.containerchoice.set_active(3)
       elif preset.container == "video/mpeg,mpegversion=2,systemstream=true":
           self.containerchoice.set_active(4)
       elif preset.container == "video/x-flv":
           self.containerchoice.set_active(5)
       elif preset.container == "video/quicktime,variant=apple":
           self.containerchoice.set_active(6)
       elif preset.container == "video/quicktime,variant=iso":
           self.containerchoice.set_active(7)
       elif preset.container == "video/quicktime,variant=3gpp":
           self.containerchoice.set_active(8)
       elif preset.container == "video/quicktime,variant=3gpp":
           self.containerchoice.set_active(9)
       elif preset.container == "application/mxf":
           self.containerchoice.set_active(10)
       elif preset.container == "video/x-ms-asf":
           self.containerchoice.set_active(11)
       else:
            print "failed to set container format"
       # print "preset.acodec.name is " + str(preset.acodec.name)
       self.codec_buttons[self.reverse_lookup(str(preset.acodec.name))].set_active(True)
       self.codec_buttons[self.reverse_lookup(str(preset.vcodec.name))].set_active(True)


       # Check for number of passes
       passes = preset.vcodec.passes
       if passes == "0":
          self.multipass = False
       else:
          self.multipass = int(passes)
          self.passcounter = int(0)

   # Create query on uridecoder to get values to populate progressbar 
   # Notes:
   # Query interface only available on uridecoder, not decodebin2)
   # FORMAT_TIME only value implemented by all plugins used
   # a lot of original code from gst-python synchronizer.py example
   def Increment_Progressbar(self):
       if self.start_time == False:  
           self.start_time = time.time()
       try:
           position, format = self._transcoder.uridecoder.query_position(gst.FORMAT_TIME)
       except:
           position = gst.CLOCK_TIME_NONE

       try:
           duration, format = self._transcoder.uridecoder.query_duration(gst.FORMAT_TIME)
       except:
           duration = gst.CLOCK_TIME_NONE
       if position != gst.CLOCK_TIME_NONE:
           value = float(position) / duration
           if float(value) < (1.0) and float(value) >= 0:
               self.ProgressBar.set_fraction(value)
               percent = (value*100)
               timespent = time.time() - self.start_time
               percent_remain = (100-percent)
               # print percent_remain
               if percent != 0:
                   rem = (timespent / percent) * percent_remain
               else: 
                   rem = 0.1
               min = rem / 60
               sec = rem % 60
               time_rem = _("%(min)d:%(sec)02d") % {
                   "min": min,
                   "sec": sec,
                   }
               if percent_remain > 0.5:
                   if self.passcounter == int(0):
                       self.ProgressBar.set_text(_("Estimated time remaining: %(time)s") % {'time': str(time_rem)})
                   else:
                       self.ProgressBar.set_text(_("Pass %(count)d time remaining: %(time)s") % {
                           'count': self.passcounter,
                           'time': str(time_rem),
                           })
               return True
           else:
               self.ProgressBar.set_fraction(0.0)
               return False
       else:
           return False

   # Call gobject.timeout_add with a value of 500millisecond to regularly poll for position so we can
   # use it for the progressbar
   def ProgressBarUpdate(self, source):
       gobject.timeout_add(500, self.Increment_Progressbar)
       # print "ProgressBar timeout_add startet"

   def _on_eos(self, source):
       context_id = self.StatusBar.get_context_id("EOS")
       if (self.multipass ==  False) or (self.passcounter == int(0)):
           self.StatusBar.push(context_id, (_("File saved to %(dir)s") % {'dir': self.videodirectory}))
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.presetchoice.set_sensitive(True)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(False)
           self.rotationchoice.set_sensitive(True)
           self.start_time = False
           self.ProgressBar.set_text(_("Done Transcoding"))
           self.ProgressBar.set_fraction(1.0)
           self.start_time = False
           self.multipass = False
           self.passcounter = False
       else:
           self.StatusBar.push(context_id, (_("Pass %(count)d Complete") % {'count': self.passcounter}))
           self.start_time = False
           self.ProgressBar.set_text(_("Start next pass"))
           if self.passcounter == (self.multipass-1):
               self.passcounter = int(0)
               self._start_transcoding()
           else:
               self.passcounter = self.passcounter+1
               self._start_transcoding()


   # Use the pygst extension 'discoverer' to get information about the incoming media. Probably need to get codec data in another way.
   # this code is probably more complex than it needs to be currently
 
   def succeed(self, d):
       if d.is_video:
           self.videodata = { 'videowidth' : d.videowidth, 'videoheight' : d.videoheight, 'videotype' : d.inputvideocaps,
                              'videolenght' : d.videolength, 'fratenum' : d.videorate.num, 'frateden' :  d.videorate.denom }
           self.videoinformation.set_markup(''.join(('<small>', _('Video width&#47;height: '), str(self.videodata['videowidth']), 
                                            "x", str(self.videodata['videoheight']), '</small>')))
           self.videocodec.set_markup(''.join(('<small>', _('Video codec: %(codec)s') % {'codec':
                                       str(gst.pbutils.get_codec_description(self.videodata['videotype']))},
                                      '</small>')))
       if d.is_audio:
           self.audiodata = { 'audiochannels' : d.audiochannels, 'samplerate' : d.audiorate, 'audiotype' : d.inputaudiocaps }
           self.audioinformation.set_markup(''.join(('<small>', _('Audio channels: %(chans)s') % {'chans': str(self.audiodata['audiochannels'])}, '</small>')))
           self.audiocodec.set_markup(''.join(('<small>', _('Audio codec: %(codec)s') % {'codec':
                                      str(gst.pbutils.get_codec_description(self.audiodata['audiotype']))}, '</small>')))
       self.discover_done=True
       if self.waiting_for_signal == True:
           if self.containertoggle == True:
               if self.container != False:
                   self.check_for_passthrough(self.container)
           else:
               self.check_for_elements()
               if self.missingtoggle==False:
                   self._start_transcoding()
       if self.container != False:
           self.check_for_passthrough(self.container)

   def discover(self, path):
       self.videodata ={}
       def discovered(d, is_media):
           if is_media:
               self.succeed(d)
       d = discoverer.Discoverer(path)
       d.connect('discovered', discovered)
       d.discover()

   def mediacheck(self, FileChosen):
       uri = urlparse (FileChosen)
       path = uri.path
       # print path
       return self.discover(path)
   
   def check_for_passthrough(self, containerchoice):
       videointersect = ("EMPTY")
       audiointersect = ("EMPTY")
       # print "container is " + str(containerchoice)
       container = codecfinder.containermap[containerchoice]
       containerelement = codecfinder.get_muxer_element(container)
       # print "container element is " + str(containerelement)
       if containerelement == False:
           self.containertoggle = True
           self.check_for_elements()
       else:
           factory = gst.registry_get_default().lookup_feature(containerelement)
           for x in factory.get_static_pad_templates():
               if (x.direction == gst.PAD_SINK):
                   sourcecaps = x.get_caps()
                   if videointersect == ("EMPTY"):
                       videointersect = sourcecaps.intersect(gst.caps_from_string(self.videodata['videotype']))
                       if videointersect != ("EMPTY"):
                           self.vsourcecaps = videointersect
                   if audiointersect == ("EMPTY"):
                       audiointersect = sourcecaps.intersect(gst.caps_from_string(self.audiodata['audiotype']))
                       if audiointersect != ("EMPTY"):
                           self.asourcecaps = audiointersect
           if videointersect == ("EMPTY"):
               self.codec_buttons["vpass"].set_sensitive(False)
           else:
               self.codec_buttons["vpass"].set_sensitive(True)
           if audiointersect == ("EMPTY"):
               self.codec_buttons["apass"].set_sensitive(False)
           else:
               self.codec_buttons["apass"].set_sensitive(True)

   # define the behaviour of the other buttons
   def on_FileChooser_file_set(self, widget):
       self.filename = self.builder.get_object ("FileChooser").get_filename()
       self.audiodata = {}
       if self.filename is not None: 
           codecinfo = self.mediacheck(self.filename)
           self.containerchoice.set_sensitive(True)
           self.presetchoice.set_sensitive(True)
           self.presetchoice.set_active(0)
           self.ProgressBar.set_fraction(0.0)
           self.ProgressBar.set_text(_("Transcoding Progress"))

   def _start_transcoding(self): 
       filechoice = self.builder.get_object ("FileChooser").get_uri()
       self.filename = self.builder.get_object ("FileChooser").get_filename()
       vheight = self.videodata['videoheight']
       vwidth = self.videodata['videowidth']
       ratenum = self.videodata['fratenum']
       ratednom = self.videodata['frateden']
       achannels = self.audiodata['audiochannels']
       if self.videopasstoggle == False:
           videocodec = codecfinder.codecmap[self.VideoCodec]
       else:
           videocodec = gst.Caps.to_string(self.vsourcecaps)
       if self.audiopasstoggle == False:
           audiocodec = codecfinder.codecmap[self.AudioCodec]
       else:
           audiocodec = gst.Caps.to_string(self.asourcecaps)
       container = self.builder.get_object ("containerchoice").get_active_text ()
       self._transcoder = transcoder_engine.Transcoder(filechoice, self.filename, self.videodirectory, container, 
                                                       audiocodec, videocodec, self.devicename, 
                                                       vheight, vwidth, ratenum, ratednom, achannels, 
                                                       self.multipass, self.passcounter, self.outputfilename,
                                                       self.timestamp, self.rotationvalue, self.audiopasstoggle, self.videopasstoggle)
       self._transcoder.connect("ready-for-querying", self.ProgressBarUpdate)
       self._transcoder.connect("got-eos", self._on_eos)
       self._transcoder.connect("got-error", self.show_error) 
       return True


   def donemessage(self, donemessage, null):
       if donemessage == gst.pbutils.INSTALL_PLUGINS_SUCCESS:
           # print "success " + str(donemessage)
           if gst.update_registry():
               print "Plugin registry updated, trying again"
           else:
               print "GStreamer registry update failed"
           if self.containertoggle == False:
               # print "done installing plugins, starting transcode"
               # FIXME - might want some test here to check plugins needed are actually installed
               # but it is a rather narrow corner case when it fails
               self._start_transcoding()
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_PARTIAL_SUCCESS:
           #print "partial success " + str(donemessage)
           self.check_for_elements()
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_NOT_FOUND:
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Plugins not found, choose different codecs."))
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(True)
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_USER_ABORT:
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Codec installation aborted."))
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(True)
       else:
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Missing plugin installation failed: ")) + gst.pbutils.InstallPluginsReturn()

   def check_for_elements(self):
       containerchoice = self.builder.get_object ("containerchoice").get_active_text ()
       containerstatus = codecfinder.get_muxer_element(codecfinder.containermap[containerchoice])
       # print "containerstatus is " + str(containerstatus)
       if self.AudioCodec != "apass":
           audiostatus = codecfinder.get_audio_encoder_element(codecfinder.codecmap[self.AudioCodec])
       else:
           audiostatus = "apass"
       if self.VideoCodec != "vpass":
           videostatus = codecfinder.get_video_encoder_element(codecfinder.codecmap[self.VideoCodec])
       else:
           videostatus= "vpass"

       if not containerstatus or not videostatus or not audiostatus:
           self.missingtoggle=True
           fail_info = []
           if self.containertoggle==True:
               audiostatus=True
               videostatus=True
           if containerstatus == False: 
               fail_info.append(gst.caps_from_string(codecfinder.containermap[containerchoice]))
           if audiostatus == False:
               fail_info.append(gst.caps_from_string(codecfinder.codecmap[self.AudioCodec]))
           if videostatus == False:
               fail_info.append(gst.caps_from_string (codecfinder.codecmap[self.VideoCodec]))
           missing = []
           for x in fail_info:
               missing.append(gst.pbutils.missing_encoder_installer_detail_new(x))
           context = gst.pbutils.InstallPluginsContext ()
           context.set_xid(self.TopWindow.get_window().xid)
           strmissing = str(missing)
           gst.pbutils.install_plugins_async (missing, context, self.donemessage, "NULL")

   # The transcodebutton is the one that calls the Transcoder class and thus starts the transcoding
   def on_transcodebutton_clicked(self, widget):
       self.containertoggle = False
       self.FileChooser.set_sensitive(False)
       self.containerchoice.set_sensitive(False)
       self.presetchoice.set_sensitive(False)
       self.CodecBox.set_sensitive(False)
       self.transcodebutton.set_sensitive(False)
       self.rotationchoice.set_sensitive(False)
       self.cancelbutton.set_sensitive(True)
       self.ProgressBar.set_fraction(0.0)
       # create a variable with a timestamp code
       timeget = datetime.datetime.now()
       self.timestamp = str(timeget.strftime("-%H%M%S-%d%m%Y"))
       # Remove suffix from inbound filename so we can reuse it together with suffix to create outbound filename
       self.nosuffix = os.path.splitext(os.path.basename(self.filename))[0]
       # pick output suffix
       container = self.builder.get_object ("containerchoice").get_active_text ()
       self.ContainerFormatSuffix = codecfinder.csuffixmap[container]
       self.outputfilename = str(self.nosuffix+self.timestamp+self.ContainerFormatSuffix)
       context_id = self.StatusBar.get_context_id("EOS")
       self.StatusBar.push(context_id, (_("Writing %(filename)s") % {'filename': self.outputfilename}))
       if self.multipass == False:
           self.ProgressBar.set_text(_("Transcoding Progress"))
       else:
           self.passcounter=int(1)
           self.ProgressBar.set_text(_("Pass %(count)d Progress") % {'count': self.passcounter})
       if self.audiodata.has_key("samplerate"):
           self.check_for_elements()
           if self.missingtoggle==False:
               self._start_transcoding()
       else:
           self.waiting_for_signal="True"

   def on_cancelbutton_clicked(self, widget):
       self.FileChooser.set_sensitive(True)
       self.containerchoice.set_sensitive(True)
       self.CodecBox.set_sensitive(True)
       self.presetchoice.set_sensitive(True)
       self.rotationchoice.set_sensitive(True)
       self.presetchoice.set_active(0)
       self.cancelbutton.set_sensitive(False)
       self._cancel_encoding = transcoder_engine.Transcoder.Pipeline(self._transcoder,"null")
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))
       context_id = self.StatusBar.get_context_id("EOS")
       self.StatusBar.pop(context_id)

   def on_containerchoice_changed(self, widget):
       self.CodecBox.set_sensitive(True)
       self.rotationchoice.set_sensitive(True)
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))
       self.container = self.builder.get_object ("containerchoice").get_active_text ()
       codecs = supported_container_map[self.container]
       self.AudioCodec = codecs[0]
       self.VideoCodec = codecs[1]
       self.transcodebutton.set_sensitive(True)
       for b in self.codec_buttons.values():
           b.set_sensitive(False)
       for c in codecs:
           self.codec_buttons[c].set_sensitive(True)
       self.codec_buttons[self.AudioCodec].set_active(True)
       self.codec_buttons[self.VideoCodec].set_active(True)
       if self.discover_done == True:
           self.check_for_passthrough(self.container)

   def on_presetchoice_changed(self, widget):
       presetchoice = self.builder.get_object ("presetchoice").get_active_text ()
       self.ProgressBar.set_fraction(0.0)
       if presetchoice == "No Presets":
           self.devicename = "nopreset"
           self.containerchoice.set_sensitive(True)
           self.start_time = False
           self.multipass = False
           self.passcounter = False
           self.rotationchoice.set_sensitive(True)
           if self.builder.get_object("containerchoice").get_active_text():
               self.CodecBox.set_sensitive(True)
               self.transcodebutton.set_sensitive(True)
       else:
           self.ProgressBar.set_fraction(0.0)
           self.devicename= self.presetchoices[presetchoice]
           # print "self.devicename is " + str(self.devicename)
           self.provide_presets(self.devicename)
           self.containerchoice.set_sensitive(False)
           self.CodecBox.set_sensitive(False)
           self.rotationchoice.set_sensitive(False)
           if self.builder.get_object("containerchoice").get_active_text():
               self.transcodebutton.set_sensitive(True)

   def on_rotationchoice_changed(self, widget):
       self.rotationvalue = self.rotationchoice.get_active()

   def on_audiobutton_pressed(self, widget, codec):
       self.AudioCodec = codec
       if self.AudioCodec == "apass":
           self.audiopasstoggle=True

   def on_videobutton_pressed(self, widget, codec):
       self.VideoCodec = codec
       if self.VideoCodec == "vpass":
           self.videopasstoggle=True
           self.rotationchoice.set_sensitive(False)
           self.rotationchoice.set_active(0)
       else:
           self.rotationchoice.set_sensitive(True)

   def on_about_dialog_activate(self, widget):
       """
           Show the about dialog.
       """
       about.AboutDialog()


   def show_error(self, NONE, error_string):
       if (error_string=="noaudioparser") or (error_string=="novideoparser"):
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.presetchoice.set_sensitive(True)
           self.rotationchoice.set_sensitive(True)
           self.presetchoice.set_active(0)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(True)
           self.ProgressBar.set_fraction(0.0)
           self.ProgressBar.set_text(_("Transcoding Progress"))
           if error_string=="noaudioparser":
               error_message = _("No audio parser, passthrough not available")
               self.codec_buttons["apass"].set_sensitive(False)
               codecs = supported_container_map[self.container]
               self.AudioCodec = codecs[0]
               self.codec_buttons[self.AudioCodec].set_active(True)
               self.audiopasstoggle = False
           elif error_string=="novideoparser":
               error_message= _("No video parser, passthrough not available")
               self.codec_buttons["vpass"].set_sensitive(False)
               codecs = supported_container_map[self.container]
               self.VideoCodec = codecs[1]
               self.codec_buttons[self.VideoCodec].set_active(True)
               self.videopasstoggle = False
           else:
               error_message=_("Uknown error")
       context_id = self.StatusBar.get_context_id("EOS")
       self.StatusBar.push(context_id, error_message)


   def on_debug_activate(self, widget):
       dotfile = "/tmp/transmageddon-debug-graph.dot"
       pngfile = "/tmp/transmageddon-pipeline.png"
       if os.access(dotfile, os.F_OK):
           os.remove(dotfile)
       if os.access(pngfile, os.F_OK):
           os.remove(pngfile)
       gst.DEBUG_BIN_TO_DOT_FILE (self._transcoder.pipeline, gst.DEBUG_GRAPH_SHOW_ALL, 'transmageddon-debug-graph')
       # check if graphviz is installed with a simple test
       try:
           dot = which.which("dot")
           os.system(dot + " -Tpng -o " + pngfile + " " + dotfile)
           gtk.show_uri(gtk.gdk.Screen(), "file://"+pngfile, 0)
       except which.WhichError:
              print "The debug feature requires graphviz (dot) to be installed."
              print "Transmageddon can not find the (dot) binary."

if __name__ == "__main__":
        hwg = TransmageddonUI()
        gtk.main()
