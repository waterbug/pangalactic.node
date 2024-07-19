README for users of the Mac version of Pangalaxian
==================================================

Installation
-----------------------------------------------------------------
To use the installer, "pgxn-MacOSX-x86_64.sh", copy it into a
directory and execute the following command:

    /bin/bash pgxn-MacOSX-x86_64.sh
-----------------------------------------------------------------

The install process will prompt you for input at certain stages:

You should accept the proposed location (simply by pressing
ENTER), which will be a directory called "pgxn" within your
home directory (/Users/[your AUID]).

When the install script has finished copying the required
libraries into that directory, it will ask "Do you wish the
installer to initalize pgxn by running conda init?  [yes|no]"
-- you should type "yes" and press ENTER, which will configure
your shell so that it can find the pangalaxian executable.

Once that is done, you should be able to simply type
"pangalaxian" in a command terminal and Pangalaxian will start up
and begin spewing its logging output to the terminal in which you
start it, and eventually the Pangalaxian GUI interface will
appear.

If the GUI interface does not appear when you run the
"pangalaxian" command, open your ".zshrc" file, which is in your
home directory, in an editor and add the following line:

export QT_MAC_WANTS_LAYER=1

Then open a new command window and execute the "pangalaxian"
command again -- the GUI should display within a minute
or two.

Switching between production and dev


