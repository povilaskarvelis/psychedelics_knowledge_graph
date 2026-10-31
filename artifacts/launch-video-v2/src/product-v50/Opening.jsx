import React from 'react';
import {Opening as PreviousOpening} from '../product-v49/Opening';

const compoundNames=[
 'Ketamine','Psilocybin','MDMA','LSD','DMT',
 'DOI','2C-B','Psilocin','DOM','25I-NBOMe',
 'Salvinorin A','Ibogaine','5-MeO-DMT','Mescaline','Ayahuasca',
];

export const Opening=(props)=> <PreviousOpening compoundNames={compoundNames} {...props}/>;
