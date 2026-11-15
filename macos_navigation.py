"""AppKit titlebar Back control; imported only by the macOS Cocoa frontend."""
import objc
from AppKit import (NSButton, NSImage, NSTitlebarAccessoryViewController,
                    NSLayoutAttributeLeft, NSImageOnly)
from Foundation import NSObject

class LumaBackTarget(NSObject):
    def goBack_(self,sender):
        self.callback()

class MacBackControl:
    def __init__(self,callback):
        self.target=LumaBackTarget.alloc().init();self.target.callback=callback
        self.window=None;self.controller=None;self.button=None;self.enabled=False

    def attach(self,qt_window):
        view=objc.objc_object(c_void_p=int(qt_window.winId()))
        window=view.window()
        if window is None:return
        if window==self.window:return
        image=NSImage.imageWithSystemSymbolName_accessibilityDescription_('chevron.backward','Back')
        button=NSButton.buttonWithImage_target_action_(image,self.target,'goBack:')
        button.setFrame_(((0,0),(36,24)))
        button.setBordered_(False);button.setImagePosition_(NSImageOnly)
        button.setToolTip_('Back (⌘[)');button.setAccessibilityLabel_('Back')
        button.setEnabled_(self.enabled)
        controller=NSTitlebarAccessoryViewController.alloc().init()
        controller.setView_(button);controller.setLayoutAttribute_(NSLayoutAttributeLeft)
        window.addTitlebarAccessoryViewController_(controller)
        self.window=window;self.controller=controller;self.button=button

    def set_enabled(self,enabled):
        self.enabled=bool(enabled)
        if self.button is not None:self.button.setEnabled_(self.enabled)
