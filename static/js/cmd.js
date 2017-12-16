function doaCmd(comand) {

    cmdimage = new Image();
    url=unescape(window.location.href);
    path = location.href.substring(0,location.href=IndexOf("/"));
    path=path +"/api/comand";

    cmdimage.onreload=new Function('window.location.replace( "'path+'" );');
    cmdimage.src = comand;
    windows.alert(path)
    return false;

}
